"""Analysis Tools

Purely deterministic: commit/file classification plus risk scoring. There is no
LLM here — every generated prose section is produced by DocumentGenerator. This
class used to construct its own LLM client for a generate_summary() method that
nothing ever called, which meant each job paid for a client (and, for the
subprocess-based providers, could fail at startup) to serve dead code.
"""

import logging
from typing import List, Dict
from src.models import ChangeCategory, Change, FileChange
from src.agent.tools.risk_analyzer import RiskAnalyzer

logger = logging.getLogger(__name__)


class AnalysisTools:
    """Tools for analyzing PR changes"""

    def __init__(self):
        """Initialize analysis tools"""
        self.risk_analyzer = RiskAnalyzer()

    def categorize_changes(self, commits: List[Dict], files: List[FileChange]) -> List[Change]:
        """Categorize commits into change categories with file details and risk assessment"""
        changes = []
        files_list = files if isinstance(files, list) else []

        for commit in commits:
            category = self._determine_category(commit["message"], [f.path for f in files_list])

            change = Change(
                title=self._extract_title(commit["message"]),
                description=self._extract_description(commit["message"]),
                category=category,
                commit_hash=commit["sha"],
                author=commit["author"],
                additions=commit.get("additions", 0),
                deletions=commit.get("deletions", 0),
                files_changed=len(files_list),
                files=files_list,
            )

            change.risk_assessment = self.risk_analyzer.analyze_change(change)
            changes.append(change)

        logger.info(f"Categorized {len(changes)} changes with risk assessment")
        return changes

    def _determine_category(self, message: str, files: List[str]) -> ChangeCategory:
        """Determine change category from commit message and files"""
        message_lower = message.lower()

        if any(kw in message_lower for kw in ["breaking", "breaking change"]):
            return ChangeCategory.BREAKING
        if any(kw in message_lower for kw in ["security", "cve", "vulnerability"]):
            return ChangeCategory.SECURITY
        if any(kw in message_lower for kw in ["perf", "performance", "optimize"]):
            return ChangeCategory.PERFORMANCE
        if any(kw in message_lower for kw in ["fix", "bug", "bugfix", "hotfix"]):
            return ChangeCategory.BUGFIX
        if any(kw in message_lower for kw in ["doc", "docs", "documentation"]):
            return ChangeCategory.DOCUMENTATION
        if any(kw in message_lower for kw in ["refactor", "refactoring"]):
            return ChangeCategory.REFACTOR
        if any(kw in message_lower for kw in ["chore", "dependencies", "build"]):
            return ChangeCategory.CHORE

        for file in files:
            if "migration" in file.lower() or "schema" in file.lower():
                return ChangeCategory.FEATURE
            if "test" in file.lower() or "spec" in file.lower():
                return ChangeCategory.CHORE

        return ChangeCategory.FEATURE

    @staticmethod
    def _extract_title(message: str) -> str:
        """Extract title from commit message"""
        return message.split('\n')[0].strip()

    @staticmethod
    def _extract_description(message: str) -> str:
        """Extract description from commit message"""
        lines = message.split('\n')
        if len(lines) > 2:
            return '\n'.join(lines[2:]).strip()
        elif len(lines) > 1:
            return lines[1].strip()
        return ""
