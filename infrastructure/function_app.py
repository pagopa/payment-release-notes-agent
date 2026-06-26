"""Azure Functions — async release plan generation via background thread + Blob Storage."""

import json
import logging
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

# Jobs still pending after this many minutes are considered lost (host recycled).
_STALE_JOB_MINUTES = int(os.getenv("STALE_JOB_MINUTES", "20"))

import azure.functions as func

_AUTH_LEVELS = {
    "anonymous": func.AuthLevel.ANONYMOUS,
    "function":  func.AuthLevel.FUNCTION,
    "admin":     func.AuthLevel.ADMIN,
}
_auth_level = _AUTH_LEVELS.get(
    os.getenv("FUNCTION_AUTH_LEVEL", "function").lower(),
    func.AuthLevel.FUNCTION,
)

app = func.FunctionApp(http_auth_level=_auth_level)
logger = logging.getLogger(__name__)

BLOB_CONTAINER = "release-notes"

# Maps job_id → threading.Event used to stop its heartbeat thread.
_heartbeat_stops: dict = {}


# ── 0. GET /api/test-llm ──────────────────────────────────────────────────────

@app.route(route="test-llm", methods=["GET"])
def test_llm(req: func.HttpRequest) -> func.HttpResponse:
    """Synchronous LLM connectivity test. Returns result or error inline (no background thread).
    Used to diagnose whether Azure Functions can reach the LLM API at all.
    """
    import requests as _requests
    import time as _time

    token = os.environ.get("GITHUB_TOKEN", "")
    model = os.environ.get("COPILOT_MODEL", "openai/chatgpt-4.1")
    url   = "https://models.github.ai/inference/chat/completions"

    if not token:
        return _error(500, "GITHUB_TOKEN not set")

    t0 = _time.time()
    try:
        resp = _requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "Reply with the single word: ok"}], "max_tokens": 5},
            timeout=30,
        )
        elapsed = _time.time() - t0
        return func.HttpResponse(
            json.dumps({
                "status_code": resp.status_code,
                "elapsed_s": round(elapsed, 2),
                "body": resp.text[:500],
            }),
            mimetype="application/json",
        )
    except Exception as exc:
        elapsed = _time.time() - t0
        return func.HttpResponse(
            json.dumps({"error": str(exc), "elapsed_s": round(elapsed, 2)}),
            status_code=502,
            mimetype="application/json",
        )


# ── 1. POST /api/generate ─────────────────────────────────────────────────────

@app.route(route="generate", methods=["POST"])
def enqueue_generate(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _error(400, "Invalid JSON body")

    platform              = body.get("platform")              or req.params.get("platform")
    pr_number             = body.get("pr_number")             or req.params.get("pr_number")
    version               = body.get("version")               or req.params.get("version") or "1.0.0"
    jira_issue_key        = body.get("jira_issue_key")        or req.params.get("jira_issue_key")        or ""
    confluence_space       = body.get("confluence_space")       or req.params.get("confluence_space")       or ""
    confluence_parent_page = body.get("confluence_parent_page") or req.params.get("confluence_parent_page") or ""
    confluence_page_title  = body.get("confluence_page_title")  or req.params.get("confluence_page_title")  or ""

    if not platform or not pr_number:
        return _error(400, "Missing required fields: platform, pr_number")

    job_id   = str(uuid.uuid4())
    conn_str = os.environ["AzureWebJobsStorage"]

    _upload_blob(conn_str, f"{job_id}.pending", b"pending")

    thread = threading.Thread(
        target=_do_generate,
        args=(conn_str, job_id, platform, pr_number, version,
              jira_issue_key, confluence_space, confluence_parent_page, confluence_page_title),
        daemon=True,  # daemon=True: dies cleanly with host instead of blocking shutdown
    )
    thread.start()

    # Heartbeat thread: updates .pending blob timestamp every 60 s so the
    # stale-job cleanup timer knows this job is still alive.
    stop_heartbeat = threading.Event()

    def _heartbeat():
        while not stop_heartbeat.wait(60):
            try:
                _upload_blob(conn_str, f"{job_id}.pending", b"pending")
            except Exception:
                pass

    hb = threading.Thread(target=_heartbeat, daemon=True)
    hb.start()
    # stop_heartbeat is set by _do_generate via a wrapper — see below
    _heartbeat_stops[job_id] = stop_heartbeat

    logger.info(
        "Started job %s for %s#%s v%s (jira=%s confluence=%s)",
        job_id, platform, pr_number, version,
        jira_issue_key or "—", confluence_space or "—",
    )

    return func.HttpResponse(
        json.dumps({
            "job_id":               job_id,
            "status":               "pending",
            "status_url":           f"/api/status/{job_id}",
            "jira_issue_key":       jira_issue_key or None,
            "confluence_space":     confluence_space or None,
        }),
        status_code=202,
        mimetype="application/json",
    )


# ── 2. GET /api/status/{job_id} ───────────────────────────────────────────────

@app.route(route="status/{job_id}", methods=["GET"])
def get_status(req: func.HttpRequest) -> func.HttpResponse:
    from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

    job_id       = req.route_params.get("job_id")
    conn_str     = os.environ["AzureWebJobsStorage"]
    blob_service = BlobServiceClient.from_connection_string(conn_str)
    container    = blob_service.get_container_client(BLOB_CONTAINER)

    if _blob_exists(container, f"{job_id}.error"):
        error_text = container.get_blob_client(f"{job_id}.error").download_blob().readall().decode()
        return func.HttpResponse(
            json.dumps({"job_id": job_id, "status": "failed", "error": error_text}),
            mimetype="application/json",
        )

    if _blob_exists(container, f"{job_id}.pdf"):
        sas = generate_blob_sas(
            account_name=blob_service.account_name,
            container_name=BLOB_CONTAINER,
            blob_name=f"{job_id}.pdf",
            account_key=blob_service.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        url = (
            f"https://{blob_service.account_name}.blob.core.windows.net"
            f"/{BLOB_CONTAINER}/{job_id}.pdf?{sas}"
        )
        return func.HttpResponse(
            json.dumps({"job_id": job_id, "status": "completed", "download_url": url}),
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps({"job_id": job_id, "status": "pending"}),
        mimetype="application/json",
    )


# ── Background worker ─────────────────────────────────────────────────────────

def _log(job_id: str, msg: str, *args, conn_str: str = None) -> None:
    formatted = msg % args if args else msg
    line = f"[INFO] {formatted}"
    logger.info(line)
    print(line, flush=True)
    if conn_str:
        try:
            _upload_blob(conn_str, f"{job_id}.pending", line.encode())
        except Exception:
            pass


def _do_generate(
    conn_str: str,
    job_id: str,
    platform: str,
    pr_number,
    version: str,
    jira_issue_key: str = "",
    confluence_space: str = "",
    confluence_parent_page: str = "",
    confluence_page_title: str = "",
) -> None:
    pr_url = f"https://github.com/{platform}/pull/{pr_number}"
    _log(job_id, "START %s v%s | jira=%s confluence=%s",
         pr_url, version, jira_issue_key or "—", confluence_space or "—", conn_str=conn_str)

    try:
        _log(job_id, "importing modules...", conn_str=conn_str)
        from src.config import config
        from src.agent.enhanced_release_notes_agent import EnhancedReleaseNotesAgent
        _log(job_id, "modules imported | LLM_PROVIDER=%s MODEL=%s",
             os.getenv("LLM_PROVIDER"), os.getenv("COPILOT_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("ANTHROPIC_MODEL"),
             conn_str=conn_str)

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, f"release_notes_{pr_number}.pdf")
            config.pdf.output_path = pdf_path
            config.pdf.enabled = True

            _log(job_id, "initializing agent...", conn_str=conn_str)
            agent = EnhancedReleaseNotesAgent()
            _log(job_id, "agent ready — calling generate_and_export", conn_str=conn_str)

            result = agent.generate_and_export(pr_url, str(version))
            _log(job_id, "generate_and_export done: %s", list(result.keys()), conn_str=conn_str)

            actual_pdf = result["pdf"]

            with open(actual_pdf, "rb") as f:
                pdf_bytes = f.read()
            _log(job_id, "PDF size=%d bytes — uploading to blob", len(pdf_bytes), conn_str=conn_str)
            _upload_blob(conn_str, f"{job_id}.pdf", pdf_bytes, content_type="application/pdf")
            _log(job_id, "blob upload done", conn_str=conn_str)

            atlassian = config.atlassian

            if jira_issue_key and atlassian.enabled:
                _log(job_id, "attaching PDF to JIRA %s", jira_issue_key)
                from src.agent.exporters.jira_exporter import JiraExporter
                JiraExporter(atlassian.url, atlassian.user, atlassian.token).attach_and_comment(
                    issue_key=jira_issue_key,
                    pdf_path=actual_pdf,
                    platform=platform,
                    pr_number=pr_number,
                    version=version,
                )
                _log(job_id, "JIRA done")
            elif jira_issue_key:
                logger.warning("[job:%s] jira_issue_key fornito ma ATLASSIAN_URL/USER/TOKEN mancanti", job_id)

            if confluence_space and atlassian.enabled:
                _log(job_id, "creating Confluence page in space %s", confluence_space)
                from src.agent.exporters.confluence_exporter import ConfluenceExporter
                page_url = ConfluenceExporter(atlassian.url, atlassian.user, atlassian.token).export(
                    release_notes=result["release_notes"],
                    space=confluence_space,
                    parent_page=confluence_parent_page or None,
                    page_title=confluence_page_title or None,
                )
                _log(job_id, "Confluence done → %s", page_url)
            elif confluence_space:
                logger.warning("[job:%s] confluence_space fornito ma ATLASSIAN_URL/USER/TOKEN mancanti", job_id)

        _delete_blob(conn_str, f"{job_id}.pending")
        _log(job_id, "COMPLETED")

    except Exception as exc:
        line = f"[ERROR] FAILED {job_id}: {exc}"
        logger.exception(line)
        print(line, flush=True)
        for _attempt in range(3):
            try:
                _upload_blob(conn_str, f"{job_id}.error", str(exc).encode())
                _delete_blob(conn_str, f"{job_id}.pending")
                break
            except Exception as upload_exc:
                print(f"[ERROR] failed to write error blob (attempt {_attempt+1}): {upload_exc}", flush=True)
                time.sleep(5)

    finally:
        stop = _heartbeat_stops.pop(job_id, None)
        if stop:
            stop.set()


# ── Blob helpers ──────────────────────────────────────────────────────────────

def _upload_blob(conn_str: str, name: str, data: bytes, content_type: str = None) -> None:
    from azure.storage.blob import BlobServiceClient, ContentSettings
    svc = BlobServiceClient.from_connection_string(conn_str)
    container = svc.get_container_client(BLOB_CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass
    cs = ContentSettings(content_type=content_type) if content_type else None
    container.upload_blob(name, data, overwrite=True, content_settings=cs)


def _delete_blob(conn_str: str, name: str) -> None:
    from azure.storage.blob import BlobServiceClient
    try:
        svc = BlobServiceClient.from_connection_string(conn_str)
        svc.get_container_client(BLOB_CONTAINER).delete_blob(name)
    except Exception:
        pass


def _blob_exists(container, name: str) -> bool:
    try:
        container.get_blob_client(name).get_blob_properties()
        return True
    except Exception:
        return False


# ── 3. Timer: mark stale pending jobs as error ────────────────────────────────

@app.timer_trigger(schedule="0 */30 * * * *", arg_name="timer", run_on_startup=False)
def cleanup_stale_jobs(timer: func.TimerRequest) -> None:
    """Convert .pending blobs older than _STALE_JOB_MINUTES to .error blobs.

    Needed because background threads are killed without raising Python
    exceptions when the Azure Functions host recycles (scale-to-zero on
    Consumption plan, timeout on any plan) — leaving .pending blobs forever.
    """
    from azure.storage.blob import BlobServiceClient

    conn_str = os.environ.get("AzureWebJobsStorage")
    if not conn_str:
        logger.warning("cleanup_stale_jobs: AzureWebJobsStorage not set, skipping")
        return

    svc = BlobServiceClient.from_connection_string(conn_str)
    container = svc.get_container_client(BLOB_CONTAINER)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_STALE_JOB_MINUTES)

    try:
        blobs = list(container.list_blobs(name_starts_with=""))
    except Exception as exc:
        logger.warning("cleanup_stale_jobs: could not list blobs: %s", exc)
        return

    for blob in blobs:
        if not blob.name.endswith(".pending"):
            continue
        last_modified = blob.last_modified
        if last_modified and last_modified < cutoff:
            job_id = blob.name[: -len(".pending")]
            error_msg = (
                f"Job timed out: still pending after {_STALE_JOB_MINUTES} minutes. "
                "The Azure Functions host likely recycled while processing a large PR."
            )
            logger.warning("Marking stale job %s as error (last_modified=%s)", job_id, last_modified)
            try:
                _upload_blob(conn_str, f"{job_id}.error", error_msg.encode())
                _delete_blob(conn_str, f"{job_id}.pending")
            except Exception as exc:
                logger.error("cleanup_stale_jobs: failed to mark %s: %s", job_id, exc)


def _error(status: int, message: str) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"error": message}),
        status_code=status,
        mimetype="application/json",
    )
