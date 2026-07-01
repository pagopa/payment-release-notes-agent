"""LLM-powered document section generator for release documentation."""

import json
import logging
import os
import re
import time
import traceback
from typing import List

logger = logging.getLogger(__name__)

_PATCH_MAX_LINES = 120
_FILES_WITH_PATCHES_MAX = 30  # max file con diff inviati all'LLM
_LLM_TIMEOUT_SECONDS = 120    # timeout per singola chiamata LLM
_LLM_MAX_RETRIES = 2          # tentativi dopo il primo fallimento
_LLM_RETRY_BACKOFF = 10       # secondi di attesa tra retry


def _truncate_patch(patch: str, max_lines: int = _PATCH_MAX_LINES) -> str:
    if not patch:
        return ""
    lines = patch.splitlines()
    if len(lines) <= max_lines:
        return patch
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"


def _is_reasoning_model(model: str) -> bool:
    if not model:
        return False
    name = model.split("/")[-1].lower()
    if name.startswith("gpt-5"):
        return True
    if name.startswith(("o1", "o3", "o4")):
        return True
    if "reasoning" in name or name.startswith("deepseek-r"):
        return True
    return False


class DocumentGenerator:
    """Generates all rich sections of a release document via LLM.

    Each public method returns a plain dict with the generated content.
    All methods fall back to empty/default values if the LLM call fails.
    """

    CONTEXTS_DIR = "./cicd_contexts"

    def __init__(self, llm_config, language: str = "Italian", cicd_context_file: str = "", github_token: str = ""):
        self.llm_config = llm_config
        self.language = language
        self._explicit_context_file = cicd_context_file
        self._github_token = github_token
        self.cicd_context = ""        # populated lazily via load_context_for_repo()
        self.llm = self._initialize_llm()

    def load_context_for_repo(self, repo_full_name: str) -> bool:
        """Resolve and load the CI/CD context for *repo_full_name*.

        Resolution order:
        1. Explicit CICD_CONTEXT_FILE env var / config value (if set and exists)
        2. cicd_contexts/<owner>_<repo>.md

        Returns True if a context was found and loaded, False otherwise. When
        False, self.cicd_context is left empty — call ensure_context_generated()
        to generate and persist one at runtime via RepoAnalyzer.
        """
        # 1. Explicit override
        if self._explicit_context_file:
            content = self._read_file(self._explicit_context_file)
            if content:
                self.cicd_context = content
                return True

        # 2. Repo-specific file
        if repo_full_name:
            slug = repo_full_name.replace("/", "_")
            repo_path = os.path.join(self.CONTEXTS_DIR, f"{slug}.md")
            content = self._read_file(repo_path)
            if content:
                logger.info(f"Using repo-specific CI/CD context: {repo_path}")
                self.cicd_context = content
                return True

        logger.warning(
            f"No CI/CD context file found for repository '{repo_full_name}' — "
            f"will be generated at runtime before enrichment."
        )
        self.cicd_context = ""
        return False

    def ensure_context_generated(self, repo_full_name: str) -> None:
        """If no CI/CD context is currently loaded, generate one at runtime via
        RepoAnalyzer and persist it to CONTEXTS_DIR/<owner>_<repo>.md so it is
        reused for subsequent invocations (until the process/container restarts).
        """
        if self.cicd_context or not repo_full_name:
            return
        if not self._github_token:
            logger.warning("Cannot auto-generate CI/CD context: no GitHub token configured")
            return

        from src.agent.tools.repo_analyzer import RepoAnalyzer

        try:
            analyzer = RepoAnalyzer(self._github_token, self)
            _, context = analyzer.analyze(repo_full_name)
        except Exception:
            logger.exception(f"Failed to auto-generate CI/CD context for {repo_full_name}")
            return

        if not context:
            # RepoAnalyzer already logged why (e.g. empty LLM response). Do not
            # persist a placeholder — retry from scratch on the next invocation.
            return

        slug = repo_full_name.replace("/", "_")
        os.makedirs(self.CONTEXTS_DIR, exist_ok=True)
        path = os.path.join(self.CONTEXTS_DIR, f"{slug}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(context)
        logger.info(f"Generated and cached CI/CD context: {path}")
        self.cicd_context = context

    @staticmethod
    def _read_file(path: str) -> str:
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return ""
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"Loaded CI/CD context: {abs_path} ({len(content)} chars)")
        return content

    # ─── LLM initialisation ───────────────────────────────────────────────────

    def _initialize_llm(self):
        provider = self.llm_config.provider
        if provider == "copilot":
            return self._create_copilot_llm()
        elif provider == "openai":
            try:
                from openai import OpenAI
                return OpenAI(api_key=self.llm_config.openai_api_key)
            except ImportError:
                raise
        elif provider == "anthropic":
            try:
                from anthropic import Anthropic
                return Anthropic(api_key=self.llm_config.anthropic_api_key)
            except ImportError:
                raise
        raise ValueError(f"Unsupported LLM provider: {provider}")

    def _create_copilot_llm(self):
        import requests

        class GitHubModelsLLM:
            API_URL = "https://models.github.ai/inference/chat/completions"

            def __init__(self, token, model):
                self.token = token
                self.model = model

            def invoke(self, prompt: str, max_tokens: int = 4096) -> str:
                is_reasoning = _is_reasoning_model(self.model)
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if is_reasoning:
                    payload["max_completion_tokens"] = max_tokens
                else:
                    payload["temperature"] = 0.2
                    payload["max_tokens"] = max_tokens

                resp = requests.post(
                    self.API_URL,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=_LLM_TIMEOUT_SECONDS,
                )
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("retry-after", 30))
                    print(f"[LLM] GitHub Models rate limit hit (429) — waiting {retry_after}s", flush=True)
                    time.sleep(retry_after)
                    raise ValueError(f"GitHub Models rate limit (429) — retry-after={retry_after}s")
                if not resp.ok:
                    raise ValueError(f"GitHub Models API error {resp.status_code}: {resp.text}")
                data = resp.json()
                return data["choices"][0]["message"]["content"]

        return GitHubModelsLLM(
            token=self.llm_config.github_token,
            model=self.llm_config.copilot_model,
        )

    # ─── Core LLM caller ──────────────────────────────────────────────────────

    def _call_llm(self, prompt: str, max_tokens: int = 4096, section: str = "unknown") -> str:
        last_exc = None
        for attempt in range(1 + _LLM_MAX_RETRIES):
            t0 = time.time()
            print(f"[LLM] section={section} attempt={attempt+1}/{1+_LLM_MAX_RETRIES} "
                  f"provider={self.llm_config.provider} max_tokens={max_tokens} "
                  f"prompt_chars={len(prompt)}", flush=True)
            try:
                result = self._call_llm_once(prompt, max_tokens)
                elapsed = time.time() - t0
                print(f"[LLM] section={section} attempt={attempt+1} OK "
                      f"elapsed={elapsed:.1f}s response_chars={len(result)}", flush=True)
                return result
            except Exception as e:
                elapsed = time.time() - t0
                last_exc = e
                exc_type = type(e).__name__
                print(f"[LLM] section={section} attempt={attempt+1} FAILED "
                      f"elapsed={elapsed:.1f}s exc={exc_type}: {e}", flush=True)
                print(f"[LLM] traceback: {traceback.format_exc()}", flush=True)
                if attempt < _LLM_MAX_RETRIES:
                    wait = _LLM_RETRY_BACKOFF * (attempt + 1)
                    print(f"[LLM] retrying in {wait}s...", flush=True)
                    time.sleep(wait)
        print(f"[LLM] section={section} gave up after {1+_LLM_MAX_RETRIES} attempts. "
              f"Last error: {type(last_exc).__name__}: {last_exc}", flush=True)
        return ""

    def _call_llm_once(self, prompt: str, max_tokens: int = 4096) -> str:
        provider = self.llm_config.provider

        if provider == "copilot":
            return self.llm.invoke(prompt, max_tokens=max_tokens)

        elif provider == "openai":
            model = self.llm_config.openai_model
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "timeout": _LLM_TIMEOUT_SECONDS,
            }
            if _is_reasoning_model(model):
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["temperature"] = 0.2
                kwargs["max_tokens"] = max_tokens
            resp = self.llm.chat.completions.create(**kwargs)
            return resp.choices[0].message.content

        elif provider == "anthropic":
            resp = self.llm.messages.create(
                model=self.llm_config.anthropic_model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                timeout=_LLM_TIMEOUT_SECONDS,
            )
            return resp.content[0].text

        raise ValueError(f"Unsupported provider: {provider}")

    def _call_llm_json(self, prompt: str, max_tokens: int = 4096, section: str = "unknown") -> dict:
        raw = self._call_llm(prompt, max_tokens, section=section)
        if not raw:
            return {}
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract the first JSON object/array
            match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            logger.warning("LLM returned non-JSON content")
            return {}

    # ─── Helpers ──────────────────────────────────────────────────────────────

    _EXCLUDED_EXTENSIONS = {".md", ".hcl"}

    def _relevant_files(self, files: list) -> list:
        return [f for f in files
                if not any(f.path.endswith(ext) for ext in self._EXCLUDED_EXTENSIONS)]

    def _files_summary(self, files: list) -> str:
        lines = []
        for f in self._relevant_files(files):
            lines.append(f"  - {f.path} [{f.status}] +{f.additions}/-{f.deletions}")
        return "\n".join(lines)

    def _files_with_patches(self, files: list) -> str:
        # Sort by total lines changed, take the most impactful files
        top = sorted(self._relevant_files(files), key=lambda f: f.additions + f.deletions, reverse=True)
        top = top[:_FILES_WITH_PATCHES_MAX]
        parts = []
        for f in top:
            header = f"### {f.path} [{f.status}] +{f.additions}/-{f.deletions}"
            patch = _truncate_patch(f.patch or "")
            parts.append(f"{header}\n{patch}" if patch else header)
        omitted = len(files) - len(top)
        if omitted > 0:
            parts.append(f"... ({omitted} smaller files omitted)")
        return "\n\n".join(parts)

    def _commits_summary(self, commits: list) -> str:
        return "\n".join(
            f"  - [{c['sha'][:7]}] {c['message'].splitlines()[0]}  ({c['author']})"
            for c in commits
        )

    # ─── Public section generators ────────────────────────────────────────────

    def generate_overview(self, pr_details: dict, commits: list, files: list) -> dict:
        """Return executive_summary, motivation_and_context, user_impact,
        environments_affected, domain."""
        lang = self.language
        cicd_block = f"\n--- CI/CD CONTEXT ---\n{self.cicd_context}\n" if self.cicd_context else ""
        prompt = f"""You are a technical writer specialising in cloud infrastructure release documentation.
Language of the output: {lang}.
{cicd_block}
Analyse this Pull Request and return a JSON object (no other text).

--- PR INFO ---
Repository: {pr_details.get('repo_full_name', 'N/A')}
PR: #{pr_details.get('number')} — {pr_details.get('title')}
Author: {pr_details.get('author')}
Source branch: {pr_details.get('head_branch', 'N/A')}
Target branch: {pr_details.get('base_branch', 'N/A')}
State: {'Draft — in revisione' if pr_details.get('draft') else pr_details.get('state', 'N/A')}
Labels: {', '.join(pr_details.get('labels', [])) or 'none'}
Stats: {pr_details.get('changed_files')} files changed, +{pr_details.get('additions')}/-{pr_details.get('deletions')} lines

--- PR DESCRIPTION ---
{pr_details.get('body') or 'N/A'}

--- COMMITS ---
{self._commits_summary(commits)}

--- FILES CHANGED ---
{self._files_summary(files)}

Return this JSON structure:
{{
  "executive_summary": "3-5 sentence executive summary of what this PR does and its business/technical impact",
  "motivation_and_context": "3-6 paragraphs explaining WHY this PR exists, the problem it solves, background, expected benefits",
  "user_impact": "Impact on end users (e.g. 'No direct user impact in production (DEV/UAT only)' or describe the impact)",
  "environments_affected": ["dev", "uat"],
  "domain": "Domain/system involved (e.g. 'Node / Core / Node Forwarder')"
}}"""

        result = self._call_llm_json(prompt, max_tokens=3000, section="overview")
        logger.info("Generated overview section")
        return result

    def generate_technical_analysis(self, files: list) -> dict:
        """Return change_details_narrative and risk_matrix."""
        lang = self.language
        prompt = f"""You are a senior cloud infrastructure engineer.
Language of the output: {lang}.
Analyse these modified files and return a JSON object (no other text).

--- FILES WITH DIFFS ---
{self._files_with_patches(files)}

Return this JSON structure:
{{
  "change_details_narrative": "Detailed technical analysis organised by stack/module. For each file or group of files describe: what was added/modified, which resources are created, key parameters, dependencies. Use plain text with clear subsection titles.",
  "risk_matrix": [
    {{
      "component": "Component or stack name",
      "risk_level": "BASSO|MEDIO|ALTO|CRITICO",
      "description": "Risk description",
      "impact": "Impact if the risk materialises",
      "mitigation": "Recommended mitigation action"
    }}
  ]
}}"""

        result = self._call_llm_json(prompt, max_tokens=6000, section="technical_analysis")
        logger.info(f"Generated technical analysis with {len(result.get('risk_matrix', []))} risk items")
        return result

    def generate_operations_guide(
        self,
        pr_details: dict,
        overview: dict,
        files: list,
        environments: List[str],
        owners: List[str],
    ) -> dict:
        """Return prerequisites, deployment_steps_by_env, rollback_plan_items, rollback_note.

        *owners* are the GitHub handles/teams resolved from the repository's
        CODEOWNERS for the files touched by this PR (see codeowners.py). May
        be empty if the repo has no CODEOWNERS or none of its rules matched.
        """
        lang = self.language
        envs = ", ".join(environments)
        owners_line = ", ".join(owners) if owners else "none found in CODEOWNERS for these files"
        cicd_block = f"\n--- CI/CD CONTEXT ---\n{self.cicd_context}\n" if self.cicd_context else ""
        prompt = f"""You are a senior DevOps engineer.
Language of the output: {lang}.
{cicd_block}
Generate the deployment and rollback plan for this PR. Return a JSON object (no other text).
Use the CI/CD context above to generate SPECIFIC commands and steps (actual script names, pipeline names, environment codes like weu-dev/weu-uat/weu-prod, real tool names).

--- PR INFO ---
Repository: {pr_details.get('repo_full_name', 'N/A')}
PR: #{pr_details.get('number')} — {pr_details.get('title')}
Author: {pr_details.get('author')}
Environments to cover: {envs}
Responsible owners (resolved from CODEOWNERS for the files touched by this PR): {owners_line}
Domain: {overview.get('domain', 'N/A')}
User impact: {overview.get('user_impact', 'N/A')}

--- FILES CHANGED ---
{self._files_summary(files)}

Return this JSON structure (only include environments that are actually affected):
{{
  "prerequisites": [
    "Prerequisite 1",
    "Prerequisite 2"
  ],
  "deployment_steps": {{
    "dev": [
      {{"order": 1, "action": "Step description", "responsible": "one of the CODEOWNERS owners above if any, otherwise a sensible placeholder", "notes": "Optional notes"}}
    ],
    "uat": [...],
    "prod": [...]
  }},
  "rollback_steps": [
    {{"order": 1, "action": "Rollback action", "environment": "dev/uat/prod/main", "responsible": "one of the CODEOWNERS owners above if any, otherwise a sensible placeholder", "notes": ""}}
  ],
  "rollback_note": "One sentence note on rollback impact (e.g. no existing resources modified)"
}}"""

        result = self._call_llm_json(prompt, max_tokens=6000, section="operations_guide")
        logger.info("Generated operations guide")
        return result

    def generate_post_deploy_verification(self, files: list, overview: dict) -> dict:
        """Return post_deploy_health_checks and monitoring_notes."""
        lang = self.language
        cicd_block = f"\n--- CI/CD CONTEXT ---\n{self.cicd_context}\n" if self.cicd_context else ""
        prompt = f"""You are a senior QA/SRE engineer.
Language of the output: {lang}.
{cicd_block}
Generate post-deploy verification checks for this release. Return a JSON object (no other text).
Use the CI/CD context to reference the actual monitoring tools and check methods used in this repo.

--- CHANGE SUMMARY ---
Domain: {overview.get('domain', 'N/A')}
Environments: {', '.join(overview.get('environments_affected', []))}
User impact: {overview.get('user_impact', 'N/A')}

--- FILES CHANGED ---
{self._files_summary(files)}

Return this JSON structure:
{{
  "health_checks": [
    {{
      "check": "Check name",
      "method": "How to verify (e.g. Azure Portal / curl / Application Insights)",
      "expected": "Expected result"
    }}
  ],
  "monitoring_notes": "What to monitor after deploy and for how long"
}}"""

        result = self._call_llm_json(prompt, max_tokens=2000, section="post_deploy_verification")
        logger.info(f"Generated {len(result.get('health_checks', []))} health checks")
        return result
