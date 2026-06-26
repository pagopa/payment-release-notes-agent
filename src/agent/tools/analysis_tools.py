"""Analysis Tools"""

import logging
from typing import List, Dict
from src.models import ChangeCategory, Change, FileChange
from src.agent.tools.risk_analyzer import RiskAnalyzer

logger = logging.getLogger(__name__)


def _is_reasoning_model(model: str) -> bool:
    """Return True for models that use the newer Chat Completions contract.

    GPT-5 and the OpenAI o-series (o1, o3, o4, ...) reject the legacy
    ``max_tokens`` parameter (they require ``max_completion_tokens``) and only
    accept the default ``temperature``. Sending ``temperature`` or
    ``max_tokens`` to these models results in an HTTP 400 error.
    """
    if not model:
        return False

    # Normalise: model ids may be prefixed with a publisher, e.g. "openai/gpt-5".
    name = model.split("/")[-1].lower()

    if name.startswith("gpt-5"):
        return True
    # o-series reasoning models: o1, o1-mini, o3, o3-mini, o4-mini, ...
    if name.startswith("o1") or name.startswith("o3") or name.startswith("o4"):
        return True
    return False


def _build_chat_payload(model: str, prompt: str) -> dict:
    """Build a Chat Completions payload compatible with the target model.

    Classic models (gpt-4o, gpt-4.1, ...) use ``temperature`` + ``max_tokens``.
    GPT-5 / o-series reasoning models use ``max_completion_tokens`` and the
    default temperature.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    if _is_reasoning_model(model):
        # Reasoning models: no custom temperature, use max_completion_tokens.
        payload["max_completion_tokens"] = 1024
    else:
        payload["temperature"] = 0.3
        payload["max_tokens"] = 1024

    return payload


class AnalysisTools:
    """Tools for analyzing PR changes"""

    def __init__(self, llm_config):
        """Initialize analysis tools"""
        self.llm_config = llm_config
        self.llm = self._initialize_llm()
        self.risk_analyzer = RiskAnalyzer()

    def _initialize_llm(self):
        """Initialize LLM based on provider"""
        if self.llm_config.provider == "copilot":
            return self._create_copilot_llm()
        elif self.llm_config.provider == "openai":
            try:
                from openai import OpenAI
                return OpenAI(api_key=self.llm_config.openai_api_key)
            except ImportError:
                logger.warning("OpenAI not installed. Install with: pip install openai")
                raise
        elif self.llm_config.provider == "anthropic":
            try:
                from anthropic import Anthropic
                return Anthropic(api_key=self.llm_config.anthropic_api_key)
            except ImportError:
                logger.warning("Anthropic not installed. Install with: pip install anthropic")
                raise
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_config.provider}")

    def _create_copilot_llm(self):
        """Create a wrapper for the GitHub Models inference API.

        Endpoint: https://models.github.ai/inference/chat/completions
        Requires a GitHub token with access to GitHub Models (github.com/marketplace/models).
        """
        import requests

        class GitHubModelsLLM:
            API_URL = "https://models.github.ai/inference/chat/completions"

            def __init__(self, token: str, model: str = "gpt-4o"):
                self.token = token
                self.model = model

            def invoke(self, prompt: str):
                headers = {
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                }
                payload = _build_chat_payload(self.model, prompt)

                response = requests.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                if not response.ok:
                    raise ValueError(
                        f"GitHub Models API error {response.status_code}: {response.text}"
                    )
                data = response.json()

                class ResponseObj:
                    def __init__(self, content):
                        self.content = content

                if "choices" in data and data["choices"]:
                    content = data["choices"][0].get("message", {}).get("content", "")
                    return ResponseObj(content)

                raise ValueError(f"Unexpected GitHub Models API response: {data}")

        return GitHubModelsLLM(
            token=self.llm_config.github_token,
            model=self.llm_config.copilot_model,
        )

    def _call_llm(self, prompt: str) -> str:
        """Call the configured LLM with a prompt and return the response text."""
        try:
            provider = self.llm_config.provider

            if provider == "copilot":
                response = self.llm.invoke(prompt)
                return response.content

            elif provider == "openai":
                model = self.llm_config.openai_model
                kwargs = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if _is_reasoning_model(model):
                    # GPT-5 / o-series: no custom temperature, use max_completion_tokens.
                    kwargs["max_completion_tokens"] = 1024
                else:
                    kwargs["temperature"] = 0.3
                    kwargs["max_tokens"] = 1024

                response = self.llm.chat.completions.create(**kwargs)
                return response.choices[0].message.content

            elif provider == "anthropic":
                response = self.llm.messages.create(
                    model=self.llm_config.anthropic_model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text

        except Exception as e:
            logger.warning(f"LLM call failed: {e}")
            return ""

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

    def generate_summary(self, changes: List[Change], pr_details: Dict) -> str:
        """Generate an AI-powered summary from changes and PR details.

        Uses the configured LLM to produce a professional release description.
        Falls back to a text-based summary if the LLM call fails.
        """
        feature_count = sum(1 for c in changes if c.category == ChangeCategory.FEATURE)
        bugfix_count = sum(1 for c in changes if c.category == ChangeCategory.BUGFIX)
        breaking_count = sum(1 for c in changes if c.category == ChangeCategory.BREAKING)
        security_count = sum(1 for c in changes if c.category == ChangeCategory.SECURITY)
        perf_count = sum(1 for c in changes if c.category == ChangeCategory.PERFORMANCE)

        changes_list = "\n".join(
            f"- [{c.category.value.upper()}] {c.title}" for c in changes[:10]
        )
        if len(changes) > 10:
            changes_list += f"\n- ... and {len(changes) - 10} more"

        pr_body = pr_details.get("body", "") or ""

        prompt = f"""You are a technical writer. Generate a concise and professional release description (3-5 sentences) for this release.

PR Title: {pr_details.get('title', 'N/A')}
PR Description: {pr_body[:500] if pr_body else 'N/A'}

Changes summary:
- {feature_count} new feature(s)
- {bugfix_count} bug fix(es)
- {breaking_count} breaking change(s)
- {security_count} security fix(es)
- {perf_count} performance improvement(s)
- Files changed: {pr_details.get('changed_files', len(changes))}, +{pr_details.get('additions', 0)}/-{pr_details.get('deletions', 0)} lines

Key changes:
{changes_list}

Write a release description suitable for a changelog or release notes document. Be concise, informative and professional."""

        logger.info("Generating AI-powered release summary...")
        ai_summary = self._call_llm(prompt)

        if ai_summary:
            logger.info("AI summary generated successfully")
            return ai_summary.strip()

        # Fallback: build summary from statistics
        logger.info("Falling back to text-based summary generation")
        parts = [f"Release based on PR #{pr_details.get('number', 'N/A')}: {pr_details.get('title', '')}"]
        parts.append(f"Total changes: {len(changes)}")
        if feature_count:
            parts.append(f"✨ {feature_count} feature(s)")
        if bugfix_count:
            parts.append(f"🐛 {bugfix_count} bugfix(es)")
        if breaking_count:
            parts.append(f"🚨 {breaking_count} breaking change(s)")
        if security_count:
            parts.append(f"🔒 {security_count} security fix(es)")
        if perf_count:
            parts.append(f"⚡ {perf_count} performance improvement(s)")
        return " - ".join(parts)

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
