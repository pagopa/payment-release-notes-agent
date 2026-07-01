"""FastAPI server — async release notes generation via blob storage job pattern."""

import logging
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

BLOB_CONTAINER     = "release-notes"
_STALE_JOB_MINUTES = int(os.getenv("STALE_JOB_MINUTES", "20"))

app = FastAPI(title="Release Notes Agent")


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def _start_cleanup_scheduler():
    conn_str = os.environ.get("AzureWebJobsStorage")
    if not conn_str:
        logger.warning("AzureWebJobsStorage not set — stale job cleanup disabled")
        return

    def _loop():
        while True:
            time.sleep(30 * 60)
            _cleanup_stale_jobs(conn_str)

    threading.Thread(target=_loop, daemon=True, name="stale-job-cleanup").start()
    logger.info("Stale job cleanup started (interval=30 min, cutoff=%d min)", _STALE_JOB_MINUTES)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}



@app.post("/api/generate", status_code=202)
def enqueue_generate(body: dict):
    conn_str = os.environ.get("AzureWebJobsStorage")
    if not conn_str:
        return JSONResponse({"error": "AzureWebJobsStorage not configured"}, status_code=500)

    platform               = body.get("platform", "")
    pr_number              = body.get("pr_number", "")
    version                = body.get("version", "1.0.0")
    jira_issue_key         = body.get("jira_issue_key", "")
    confluence_space       = body.get("confluence_space", "")
    confluence_parent_page = body.get("confluence_parent_page", "")
    confluence_page_title  = body.get("confluence_page_title", "")

    if not platform or not pr_number:
        return JSONResponse({"error": "Missing required fields: platform, pr_number"}, status_code=400)

    job_id = str(uuid.uuid4())
    _upload_blob(conn_str, f"{job_id}.pending", b"pending")

    pr_url = f"https://github.com/{platform}/pull/{pr_number}"

    agent               = None
    release_notes       = None
    gh_context          = None
    placeholder_created = False
    confluence_page_url = None
    resolved_page_title = confluence_page_title or None

    if confluence_space:
        try:
            from src.config import config
            atlassian = config.atlassian
            if atlassian.enabled:
                from src.agent.enhanced_release_notes_agent import EnhancedReleaseNotesAgent
                from src.agent.exporters.confluence_exporter import ConfluenceExporter

                agent = EnhancedReleaseNotesAgent()
                release_notes, gh_context = agent.prepare_release_notes(pr_url, str(version))
                resolved_page_title = confluence_page_title or \
                    f"Release Notes — {release_notes.repo_full_name or platform} PR#{pr_number}"

                confluence_page_url = ConfluenceExporter(
                    atlassian.url, atlassian.user, atlassian.token
                ).export(
                    release_notes=release_notes,
                    space=confluence_space,
                    parent_page=confluence_parent_page or None,
                    page_title=resolved_page_title,
                    placeholder=True,
                )
                placeholder_created = True
                logger.info("Confluence placeholder created synchronously → %s", confluence_page_url)
            else:
                logger.warning("confluence_space provided but ATLASSIAN_URL/USER/TOKEN missing — placeholder skipped")
        except Exception as exc:
            # Fallback: il worker creerà e aggiornerà la pagina in modo asincrono
            logger.exception("Synchronous Confluence placeholder creation failed: %s", exc)
            agent = release_notes = gh_context = None
            placeholder_created = False

    threading.Thread(
        target=_do_generate,
        args=(conn_str, job_id, platform, pr_number, version,
              jira_issue_key, confluence_space, confluence_parent_page, resolved_page_title or ""),
        kwargs={
            "agent":               agent,
            "release_notes":       release_notes,
            "gh_context":          gh_context,
            "placeholder_created": placeholder_created,
        },
        daemon=True,
        name=f"job-{job_id[:8]}",
    ).start()

    logger.info("Started job %s for %s#%s v%s", job_id, platform, pr_number, version)
    return JSONResponse({
        "job_id":           job_id,
        "status":           "pending",
        "status_url":       f"/api/status/{job_id}",
        "jira_issue_key":   jira_issue_key or None,
        "confluence_space": confluence_space or None,
        "confluence_url":   confluence_page_url,
    }, status_code=202)


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

    conn_str = os.environ.get("AzureWebJobsStorage")
    if not conn_str:
        return JSONResponse({"error": "AzureWebJobsStorage not configured"}, status_code=500)

    blob_service = BlobServiceClient.from_connection_string(conn_str)
    container    = blob_service.get_container_client(BLOB_CONTAINER)

    if _blob_exists(container, f"{job_id}.error"):
        error_text = container.get_blob_client(f"{job_id}.error").download_blob().readall().decode()
        return {"job_id": job_id, "status": "failed", "error": error_text}

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
        return {"job_id": job_id, "status": "completed", "download_url": url}

    return {"job_id": job_id, "status": "pending"}


# ── Worker ────────────────────────────────────────────────────────────────────

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
    conn_str, job_id, platform, pr_number, version,
    jira_issue_key="", confluence_space="", confluence_parent_page="", confluence_page_title="",
    agent=None, release_notes=None, gh_context=None, placeholder_created=False,
):
    pr_url = f"https://github.com/{platform}/pull/{pr_number}"
    _log(job_id, "START %s v%s | jira=%s confluence=%s",
         pr_url, version, jira_issue_key or "—", confluence_space or "—", conn_str=conn_str)

    stop_heartbeat = threading.Event()

    def _heartbeat():
        while not stop_heartbeat.wait(60):
            try:
                _upload_blob(conn_str, f"{job_id}.pending", b"pending")
            except Exception:
                pass

    threading.Thread(target=_heartbeat, daemon=True, name=f"hb-{job_id[:8]}").start()

    # Stato condiviso per la gestione della pagina Confluence (placeholder/update/errore)
    confluence_ctx = {
        "exporter":      None,
        "release_notes": release_notes,
        "page_title":    confluence_page_title or None,
        "page_url":      None,
    }

    try:
        _log(job_id, "importing modules...", conn_str=conn_str)
        from src.config import config
        from src.agent.enhanced_release_notes_agent import EnhancedReleaseNotesAgent
        _log(job_id, "modules imported | LLM_PROVIDER=%s MODEL=%s",
             os.getenv("LLM_PROVIDER"),
             os.getenv("COPILOT_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("ANTHROPIC_MODEL"),
             conn_str=conn_str)

        atlassian = config.atlassian

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, f"release_notes_{pr_number}.pdf")
            config.pdf.output_path = pdf_path
            config.pdf.enabled = True

            # ── Agente + dati GitHub: riusa quelli preparati sincronamente ─────
            if agent is None:
                _log(job_id, "initializing agent...", conn_str=conn_str)
                agent = EnhancedReleaseNotesAgent()
                _log(job_id, "agent ready", conn_str=conn_str)

            if release_notes is None or gh_context is None:
                _log(job_id, "preparing release notes (GitHub data)...", conn_str=conn_str)
                release_notes, gh_context = agent.prepare_release_notes(pr_url, str(version))
                confluence_ctx["release_notes"] = release_notes
            else:
                _log(job_id, "reusing release notes prepared synchronously", conn_str=conn_str)

            # ── Confluence placeholder (solo se non già creato sincronamente) ──
            if confluence_space and atlassian.enabled:
                from src.agent.exporters.confluence_exporter import ConfluenceExporter
                page_title = confluence_page_title or \
                    f"Release Notes — {release_notes.repo_full_name or platform} PR#{pr_number}"
                confluence_ctx["page_title"] = page_title
                confluence_ctx["exporter"] = ConfluenceExporter(
                    atlassian.url, atlassian.user, atlassian.token
                )
                if not placeholder_created:
                    _log(job_id, "creating Confluence placeholder page in space %s", confluence_space, conn_str=conn_str)
                    page_url = confluence_ctx["exporter"].export(
                        release_notes=release_notes,
                        space=confluence_space,
                        parent_page=confluence_parent_page or None,
                        page_title=page_title,
                        placeholder=True,
                    )
                    confluence_ctx["page_url"] = page_url
                    _log(job_id, "Confluence placeholder ready → %s", page_url, conn_str=conn_str)
                else:
                    _log(job_id, "Confluence placeholder already created synchronously — will update", conn_str=conn_str)
            elif confluence_space:
                logger.warning("[job:%s] confluence_space provided but ATLASSIAN_URL/USER/TOKEN missing", job_id)

            # ── Arricchimento LLM ──────────────────────────────────────────────
            _log(job_id, "enriching release notes (LLM)...", conn_str=conn_str)
            agent.enrich_release_notes(release_notes, gh_context)
            _log(job_id, "LLM enrichment done", conn_str=conn_str)

            # ── Export PDF/JSON ────────────────────────────────────────────────
            result = agent.export_release_notes(release_notes)
            _log(job_id, "export done: %s", list(result.keys()), conn_str=conn_str)

            actual_pdf = result["pdf"]
            with open(actual_pdf, "rb") as f:
                pdf_bytes = f.read()
            _log(job_id, "PDF size=%d bytes — uploading to blob", len(pdf_bytes), conn_str=conn_str)
            _upload_blob(conn_str, f"{job_id}.pdf", pdf_bytes, content_type="application/pdf")
            _log(job_id, "blob upload done", conn_str=conn_str)

            if jira_issue_key and atlassian.enabled:
                _log(job_id, "attaching PDF to JIRA %s", jira_issue_key, conn_str=conn_str)
                from src.agent.exporters.jira_exporter import JiraExporter
                JiraExporter(atlassian.url, atlassian.user, atlassian.token).attach_and_comment(
                    issue_key=jira_issue_key,
                    pdf_path=actual_pdf,
                    platform=platform,
                    pr_number=pr_number,
                    version=version,
                )
                _log(job_id, "JIRA done", conn_str=conn_str)
            elif jira_issue_key:
                logger.warning("[job:%s] jira_issue_key provided but ATLASSIAN_URL/USER/TOKEN missing", job_id)

            # ── Aggiorna la pagina Confluence col contenuto completo ───────────
            if confluence_ctx["exporter"]:
                _log(job_id, "updating Confluence page with full content", conn_str=conn_str)
                page_url = confluence_ctx["exporter"].export(
                    release_notes=release_notes,
                    space=confluence_space,
                    parent_page=confluence_parent_page or None,
                    page_title=confluence_ctx["page_title"],
                )
                confluence_ctx["page_url"] = page_url
                _log(job_id, "Confluence done → %s", page_url, conn_str=conn_str)

        _delete_blob(conn_str, f"{job_id}.pending")
        _log(job_id, "COMPLETED")

    except Exception as exc:
        line = f"[ERROR] FAILED {job_id}: {exc}"
        logger.exception(line)
        print(line, flush=True)

        # Se la pagina Confluence placeholder era già stata creata, aggiornala con
        # una nota di errore invece di lasciarla in stato "Generazione in corso…".
        if confluence_ctx["exporter"] and confluence_ctx["release_notes"] is not None:
            try:
                confluence_ctx["exporter"].export(
                    release_notes=confluence_ctx["release_notes"],
                    space=confluence_space,
                    parent_page=confluence_parent_page or None,
                    page_title=confluence_ctx["page_title"],
                    error_message=str(exc),
                )
                logger.info("[job:%s] Confluence page updated with error note", job_id)
            except Exception as conf_exc:
                logger.error("[job:%s] failed to update Confluence page with error: %s",
                             job_id, conf_exc)

        for attempt in range(3):
            try:
                _upload_blob(conn_str, f"{job_id}.error", str(exc).encode())
                _delete_blob(conn_str, f"{job_id}.pending")
                break
            except Exception as upload_exc:
                print(f"[ERROR] failed to write error blob (attempt {attempt+1}): {upload_exc}", flush=True)
                time.sleep(5)

    finally:
        stop_heartbeat.set()


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
        BlobServiceClient.from_connection_string(conn_str) \
            .get_container_client(BLOB_CONTAINER).delete_blob(name)
    except Exception:
        pass


def _blob_exists(container, name: str) -> bool:
    try:
        container.get_blob_client(name).get_blob_properties()
        return True
    except Exception:
        return False


# ── Stale job cleanup ─────────────────────────────────────────────────────────

def _cleanup_stale_jobs(conn_str: str) -> None:
    from azure.storage.blob import BlobServiceClient
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
        if blob.last_modified and blob.last_modified < cutoff:
            job_id = blob.name[: -len(".pending")]
            logger.warning("Marking stale job %s as error (last_modified=%s)", job_id, blob.last_modified)
            try:
                _upload_blob(conn_str, f"{job_id}.error",
                             f"Job timed out after {_STALE_JOB_MINUTES} minutes.".encode())
                _delete_blob(conn_str, f"{job_id}.pending")
            except Exception as exc:
                logger.error("cleanup_stale_jobs: failed to mark %s: %s", job_id, exc)
