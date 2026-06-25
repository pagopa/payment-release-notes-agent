"""Azure Functions — async release plan generation via background thread + Blob Storage."""

import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timedelta, timezone

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
        daemon=False,
    )
    thread.start()

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

def _log(job_id: str, msg: str, *args) -> None:
    formatted = msg % args if args else msg
    line = f"[INFO] {formatted}"
    logger.info(line)
    print(line, flush=True)


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
         pr_url, version, jira_issue_key or "—", confluence_space or "—")

    try:
        _log(job_id, "importing modules...")
        from src.config import config
        from src.agent.enhanced_release_notes_agent import EnhancedReleaseNotesAgent
        _log(job_id, "modules imported | LLM_PROVIDER=%s MODEL=%s",
             os.getenv("LLM_PROVIDER"), os.getenv("COPILOT_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("ANTHROPIC_MODEL"))

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, f"release_notes_{pr_number}.pdf")
            config.pdf.output_path = pdf_path
            config.pdf.enabled = True

            _log(job_id, "initializing agent...")
            agent = EnhancedReleaseNotesAgent()
            _log(job_id, "agent ready — calling generate_and_export")

            result = agent.generate_and_export(pr_url, str(version))
            _log(job_id, "generate_and_export done: %s", list(result.keys()))

            actual_pdf = result["pdf"]

            with open(actual_pdf, "rb") as f:
                pdf_bytes = f.read()
            _log(job_id, "PDF size=%d bytes — uploading to blob", len(pdf_bytes))
            _upload_blob(conn_str, f"{job_id}.pdf", pdf_bytes, content_type="application/pdf")
            _log(job_id, "blob upload done")

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
        _append_log(job_id, f"FAILED: {exc}")
        _upload_blob(conn_str, f"{job_id}.error", str(exc).encode())
        _delete_blob(conn_str, f"{job_id}.pending")


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


def _error(status: int, message: str) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"error": message}),
        status_code=status,
        mimetype="application/json",
    )
