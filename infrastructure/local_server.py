"""Local development server — mirrors the Azure Function endpoint via FastAPI."""

import logging
import os
import tempfile

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = FastAPI(title="Release Notes Agent (local)")


class GenerateRequest(BaseModel):
    platform: str
    pr_number: int
    version: str = "1.0.0"
    jira_issue_key: str = ""
    confluence_space: str = ""
    confluence_parent_page: str = ""
    confluence_page_title: str = ""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/generate")
def generate_release_plan(req: GenerateRequest):
    """Generate a release plan PDF from a GitHub PR.

    Body:
        platform   — GitHub owner/repo  e.g. "pagopa/p4pa-infra"
        pr_number  — Pull Request number
        version    — Release version (default "1.0.0")
    """
    pr_url = f"https://github.com/{req.platform}/pull/{req.pr_number}"
    logger.info("Generating release plan for %s v%s", pr_url, req.version)

    try:
        from src.config import config
        from src.agent.enhanced_release_notes_agent import EnhancedReleaseNotesAgent

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, f"release_notes_{req.pr_number}.pdf")
            config.pdf.output_path = pdf_path
            config.pdf.enabled = True

            agent = EnhancedReleaseNotesAgent()
            result = agent.generate_and_export(pr_url, req.version)

            actual_pdf = result["pdf"]

            atlassian = config.atlassian

            if req.jira_issue_key and atlassian.enabled:
                logger.info("Attaching PDF to JIRA %s", req.jira_issue_key)
                from src.agent.exporters.jira_exporter import JiraExporter
                JiraExporter(atlassian.url, atlassian.user, atlassian.token).attach_and_comment(
                    issue_key=req.jira_issue_key,
                    pdf_path=actual_pdf,
                    platform=req.platform,
                    pr_number=req.pr_number,
                    version=req.version,
                )
            elif req.jira_issue_key:
                logger.warning("jira_issue_key fornito ma ATLASSIAN_URL/USER/TOKEN mancanti")

            if req.confluence_space and atlassian.enabled:
                logger.info("Creando pagina Confluence in spazio %s", req.confluence_space)
                from src.agent.exporters.confluence_exporter import ConfluenceExporter
                page_url = ConfluenceExporter(atlassian.url, atlassian.user, atlassian.token).export(
                    release_notes=result["release_notes"],
                    space=req.confluence_space,
                    parent_page=req.confluence_parent_page or None,
                    page_title=req.confluence_page_title or None,
                )
                logger.info("Confluence pagina creata → %s", page_url)
            elif req.confluence_space:
                logger.warning("confluence_space fornito ma ATLASSIAN_URL/USER/TOKEN mancanti")

            with open(actual_pdf, "rb") as f:
                pdf_content = f.read()

        filename = f"release_notes_{req.platform.replace('/', '_')}_{req.pr_number}.pdf"
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as exc:
        logger.exception("Error generating release plan")
        return JSONResponse(status_code=500, content={"error": str(exc)})
