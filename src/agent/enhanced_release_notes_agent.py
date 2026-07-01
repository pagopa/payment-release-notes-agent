"""Enhanced Release Notes Agent with LLM-generated deployment documentation."""

import json
import logging
from datetime import datetime
from typing import Optional

from src.config import config
from src.models import ReleaseNotes
from src.agent.tools.github_tools import GitHubTools
from src.agent.tools.analysis_tools import AnalysisTools
from src.agent.tools.document_generator import DocumentGenerator
from src.agent.exporters.enhanced_pdf_exporter import EnhancedPDFExporter

logger = logging.getLogger(__name__)


class EnhancedReleaseNotesAgent:
    """Enhanced agent that uses the LLM to generate all document sections
    (executive summary, motivation, risk matrix, deployment guide, rollback,
    post-deploy verification) from the actual PR diffs."""

    def __init__(self):
        config.validate()
        self.github_tools = GitHubTools(config.github.token)
        self.analysis_tools = AnalysisTools(config.llm)
        self.document_generator = DocumentGenerator(
            llm_config=config.llm,
            language=config.llm.document_language,
            cicd_context_file=config.llm.cicd_context_file,
            github_token=config.github.token,
        )
        self.pdf_exporter = EnhancedPDFExporter()

    def prepare_release_notes(self, pr_url: str, version: str) -> tuple:
        logger.info(f"Preparing release notes (GitHub data) for {pr_url}")

        owner, repo, pr_number = self.github_tools.extract_repo_and_pr_from_url(pr_url)

        pr_details = self.github_tools.get_pr_details(owner, repo, pr_number)
        logger.info(f"Fetched PR #{pr_details['number']}: {pr_details['title']}")

        # Load the best-matching CI/CD context for this repo
        repo_full_name = pr_details.get("repo_full_name", f"{owner}/{repo}")
        self.document_generator.load_context_for_repo(repo_full_name)
        logger.info(f"CI/CD context loaded for {repo_full_name}")

        commits = self.github_tools.get_pr_commits(owner, repo, pr_number)
        files = self.github_tools.get_pr_files(owner, repo, pr_number)
        logger.info(f"Fetched {len(commits)} commits and {len(files)} files")

        # ── Categorise changes (keyword-based, for the changes section) ──────
        changes = self.analysis_tools.categorize_changes(commits, files)

        # ── Build base ReleaseNotes ───────────────────────────────────────────
        release_notes = ReleaseNotes(
            version=version,
            title=pr_details.get("title", f"Release {version}"),
            summary="",
            release_date=datetime.now(),
            pr_url=pr_url,
            pr_number=pr_details["number"],
            pr_author=pr_details.get("author", ""),
            pr_body=pr_details.get("body", ""),
            source_branch=pr_details.get("head_branch", ""),
            target_branch=pr_details.get("base_branch", ""),
            repo_full_name=pr_details.get("repo_full_name", ""),
            pr_labels=pr_details.get("labels", []),
            pr_draft=pr_details.get("draft", False),
        )

        for change in changes:
            release_notes.add_change(change)

        release_notes.files_changed = len(files)
        release_notes.additions = pr_details.get("additions", 0)
        release_notes.deletions = pr_details.get("deletions", 0)

        context = {"pr_details": pr_details, "commits": commits, "files": files}
        return release_notes, context

    def enrich_release_notes(self, release_notes: ReleaseNotes, context: dict) -> ReleaseNotes:
        """Phase 2 — enrich the ReleaseNotes with all LLM-generated sections."""
        pr_details = context["pr_details"]
        commits = context["commits"]
        files = context["files"]

        # Generate (and cache to disk) the CI/CD context here if it wasn't found
        # on disk during prepare_release_notes — this runs in the async worker,
        # after the Confluence placeholder URL has already been returned.
        self.document_generator.ensure_context_generated(release_notes.repo_full_name)

        environments = [e.strip() for e in config.llm.environments.split(",") if e.strip()]

        # ── LLM: overview ─────────────────────────────────────────────────────
        logger.info("Generating overview section...")
        overview = self.document_generator.generate_overview(pr_details, commits, files)
        release_notes.summary = overview.get("executive_summary", "")
        release_notes.motivation_and_context = overview.get("motivation_and_context", "")
        release_notes.user_impact = overview.get("user_impact", "")
        release_notes.environments_affected = overview.get("environments_affected", [])
        release_notes.domain = overview.get("domain", "")

        # ── LLM: technical analysis ───────────────────────────────────────────
        logger.info("Generating technical analysis...")
        tech = self.document_generator.generate_technical_analysis(files)
        release_notes.change_details_narrative = tech.get("change_details_narrative", "")
        release_notes.risk_matrix_items = tech.get("risk_matrix", [])

        # ── LLM: operations guide ─────────────────────────────────────────────
        logger.info("Generating operations guide...")
        ops = self.document_generator.generate_operations_guide(
            pr_details=pr_details,
            overview=overview,
            files=files,
            environments=environments,
            responsible_team=config.llm.responsible_team,
        )
        release_notes.deployment_prerequisites = ops.get("prerequisites", [])
        release_notes.deployment_steps_by_env = ops.get("deployment_steps", {})
        release_notes.rollback_plan_items = ops.get("rollback_steps", [])
        release_notes.rollback_note = ops.get("rollback_note", "")

        # ── LLM: post-deploy verification ─────────────────────────────────────
        logger.info("Generating post-deploy verification...")
        verify = self.document_generator.generate_post_deploy_verification(files, overview)
        release_notes.post_deploy_health_checks = verify.get("health_checks", [])
        release_notes.monitoring_notes = verify.get("monitoring_notes", "")

        return release_notes

    def export_release_notes(self, release_notes: ReleaseNotes) -> dict:
        """Phase 3 — export the (enriched) ReleaseNotes to PDF + JSON."""
        logger.info("Exporting to PDF...")
        pdf_path = self.pdf_exporter.export(release_notes, config.pdf.output_path)

        json_path = config.pdf.output_path.replace(".pdf", ".json")
        with open(json_path, "w") as f:
            json.dump(release_notes.to_dict(), f, indent=2, default=str)

        logger.info("Enhanced release notes generated successfully")
        return {
            "pdf": pdf_path,
            "json": json_path,
            "release_notes": release_notes,
        }

    def generate_and_export(self, pr_url: str, version: str) -> dict:

        logger.info(f"Starting enhanced release notes generation for {pr_url}")
        release_notes, context = self.prepare_release_notes(pr_url, version)
        self.enrich_release_notes(release_notes, context)
        return self.export_release_notes(release_notes)

    def process_pr_url(self, pr_url: str, version: Optional[str] = None) -> ReleaseNotes:
        result = self.generate_and_export(pr_url, version or config.release.version)
        return result["release_notes"]
