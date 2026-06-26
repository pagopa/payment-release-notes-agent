"""Basic Release Notes Agent — orchestrates GitHub fetch, LLM analysis and PDF export."""

import logging
from datetime import datetime
from typing import Optional
from src.config import config
from src.models import ReleaseNotes
from src.agent.tools.github_tools import GitHubTools
from src.agent.tools.analysis_tools import AnalysisTools
from src.agent.exporters.pdf_exporter import PDFExporter

logger = logging.getLogger(__name__)


class ReleaseNotesAgent:
    """Generates release notes from a GitHub PR and exports them to PDF."""

    def __init__(self):
        config.validate()
        self.github_tools = GitHubTools(config.github.token)
        self.analysis_tools = AnalysisTools(config.llm)
        self.pdf_exporter = PDFExporter()

    def process_pr_url(self, pr_url: str, version: Optional[str] = None) -> ReleaseNotes:
        logger.info(f"Processing PR: {pr_url}")

        # Extract PR info from URL
        owner, repo, pr_number = self.github_tools.extract_repo_and_pr_from_url(pr_url)
        logger.info(f"Extracted: {owner}/{repo}#{pr_number}")

        # Fetch PR details
        pr_details = self.github_tools.get_pr_details(owner, repo, pr_number)
        logger.info(f"PR Title: {pr_details['title']}")

        # Fetch commits and files
        commits = self.github_tools.get_pr_commits(owner, repo, pr_number)
        files = self.github_tools.get_pr_files(owner, repo, pr_number)
        logger.info(f"Fetched {len(commits)} commits and {len(files)} files")

        # Categorize changes
        changes = self.analysis_tools.categorize_changes(commits, files)
        logger.info(f"Categorized {len(changes)} changes")

        for change in changes:
            logger.debug(f"  Change: '{change.title}' -> Category: {change.category}")

        # Generate AI-powered summary
        summary = self.analysis_tools.generate_summary(changes, pr_details)
        logger.info("Generated summary")

        # Create release notes object
        release_notes = ReleaseNotes(
            version=version or config.release.version,
            title=f"Release {version or config.release.version}",
            summary=summary,
            release_date=datetime.now(),
            pr_url=pr_url,
            pr_number=pr_number,
            pr_author=pr_details.get("author"),
            pr_body=pr_details.get("body"),
        )

        # Add changes to release notes
        logger.debug(f"Adding {len(changes)} changes to release_notes...")
        for change in changes:
            release_notes.add_change(change)
            logger.debug(f"  Added: {change.title} ({change.category})")

        logger.debug(
            f"Release notes contents — "
            f"features={len(release_notes.features)}, "
            f"bugfixes={len(release_notes.bugfixes)}, "
            f"breaking={len(release_notes.breaking_changes)}, "
            f"security={len(release_notes.security_fixes)}, "
            f"performance={len(release_notes.performance_improvements)}, "
            f"docs={len(release_notes.documentation)}, "
            f"refactor={len(release_notes.refactoring)}, "
            f"chores={len(release_notes.chores)}"
        )

        # Update statistics
        release_notes.files_changed = len(files)
        release_notes.additions = pr_details['additions']
        release_notes.deletions = pr_details['deletions']

        logger.info(f"Release notes created: v{release_notes.version}")
        return release_notes

    def generate_and_export(self, pr_url: str, version: Optional[str] = None) -> dict:
        release_notes = self.process_pr_url(pr_url, version)

        result = {
            "version": release_notes.version,
            "pr_number": release_notes.pr_number,
            "files": {},
        }

        if config.pdf.enabled:
            pdf_path = self.pdf_exporter.export(release_notes, config.pdf.output_path)
            result["files"]["pdf"] = pdf_path
            logger.info(f"PDF exported to: {pdf_path}")

        return result
