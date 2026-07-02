"""Repo analyzer — fetches key CI/CD files from a GitHub repo and generates
a cicd_context.md via LLM."""

import logging
import re
from typing import Optional
from github import Github, GithubException

logger = logging.getLogger(__name__)

# Max chars to include per file in the LLM prompt
_FILE_MAX_CHARS = 6000
# Max total chars of fetched content sent to LLM
_TOTAL_MAX_CHARS = 40000

# Candidate paths to fetch, in priority order
_CANDIDATE_FILES = [
    "README.md",
    "CODEOWNERS",
    "release_deploy.yml",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    ".terraform-version",
]

_CANDIDATE_DIRS = [
    ".github/workflows",
    ".devops",
    "scripts",
    ".utils",
    "deploy",
    "deployment",
    "ci",
]


def _truncate(text: str, max_chars: int = _FILE_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [truncated, {len(text) - max_chars} more chars]"


class RepoAnalyzer:
    """Fetches CI/CD-relevant files from a GitHub repo and generates
    a structured cicd_context.md using the LLM."""

    def __init__(self, github_token: str, document_generator):
        self.gh = Github(github_token)
        self.doc_gen = document_generator

    # ── Public entry point ────────────────────────────────────────────────────

    def analyze(self, repo_url: str) -> tuple[str, Optional[str]]:
        """Analyze *repo_url* and return (repo_full_name, context_markdown).

        context_markdown is None if the repository is inaccessible or the LLM
        failed to produce a context — callers must not persist a None result.
        """
        owner, repo_name = self._parse_repo_url(repo_url)
        repo_full_name = f"{owner}/{repo_name}"
        logger.info(f"Analyzing repo: {repo_full_name}")

        try:
            repo = self.gh.get_repo(repo_full_name)
        except GithubException as e:
            raise ValueError(f"Cannot access repository '{repo_full_name}': {e}") from e

        content_map = self._fetch_content(repo)

        logger.info(f"Fetched {len(content_map)} files/dirs ({sum(len(v) for v in content_map.values())} chars total)")
        context = self._generate_context(repo_full_name, content_map)
        return repo_full_name, context

    # ── GitHub fetching ───────────────────────────────────────────────────────

    def _fetch_content(self, repo) -> dict:
        content_map = {}
        total = 0

        # Individual files
        for path in _CANDIDATE_FILES:
            if total >= _TOTAL_MAX_CHARS:
                break
            text = self._get_file(repo, path)
            if text:
                content_map[path] = _truncate(text)
                total += len(content_map[path])

        # Directories — list contents and read text files
        for dir_path in _CANDIDATE_DIRS:
            if total >= _TOTAL_MAX_CHARS:
                break
            items = self._list_dir(repo, dir_path)
            if not items:
                continue
            for item in items[:12]:          # max 12 files per dir
                if total >= _TOTAL_MAX_CHARS:
                    break
                if item.type == "file" and self._is_text_file(item.name):
                    text = self._get_file(repo, item.path)
                    if text:
                        content_map[item.path] = _truncate(text, 3000)
                        total += len(content_map[item.path])

        # Top-level directory listing (to infer structure)
        top_items = self._list_dir(repo, "")
        if top_items:
            listing = "\n".join(
                f"{'[DIR] ' if i.type == 'dir' else ''}{i.path}" for i in top_items
            )
            content_map["[ROOT LISTING]"] = listing

        # src/ structure (one level deep)
        src_items = self._list_dir(repo, "src")
        if src_items:
            listing = "\n".join(
                f"{'[DIR] ' if i.type == 'dir' else ''}{i.path}" for i in src_items[:40]
            )
            content_map["[SRC LISTING]"] = listing

        return content_map

    def _get_file(self, repo, path: str) -> Optional[str]:
        try:
            f = repo.get_contents(path)
            if isinstance(f, list):
                return None
            if f.size > 200_000:
                return None
            return f.decoded_content.decode("utf-8", errors="replace")
        except GithubException:
            return None

    def _list_dir(self, repo, path: str) -> list:
        try:
            items = repo.get_contents(path)
            return items if isinstance(items, list) else [items]
        except GithubException:
            return []

    @staticmethod
    def _is_text_file(name: str) -> bool:
        exts = {".yml", ".yaml", ".sh", ".md", ".json", ".tf", ".py",
                ".js", ".ts", ".go", ".java", ".ini", ".toml", ".hcl"}
        return any(name.endswith(e) for e in exts) or "." not in name

    @staticmethod
    def _parse_repo_url(url: str) -> tuple[str, str]:
        url = url.rstrip("/")
        # Accept: https://github.com/owner/repo or owner/repo
        match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
        if match:
            return match.group(1), match.group(2).removesuffix(".git")
        parts = url.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
        raise ValueError(f"Cannot parse repo URL: {url}")

    # ── LLM synthesis ─────────────────────────────────────────────────────────

    def _generate_context(self, repo_full_name: str, content_map: dict) -> Optional[str]:
        files_block = "\n\n".join(
            f"### {path}\n{content}" for path, content in content_map.items()
        )

        prompt = f"""You are a senior DevOps engineer at PagoPA, the company running Italy's national digital payments platform.
Analyse the files below from the GitHub repository `{repo_full_name}` and write a comprehensive CI/CD context document in Markdown.

The document will be used to generate accurate release and deployment documentation for every PR in this repo.
Be specific — use actual file names, script names, environment names, tool names found in the files.

--- PAGOPA TECHNOLOGY CONTEXT (use to interpret the files; do NOT assume any of it applies unless the files support it) ---
- Cloud-native only: application workloads are deployed to Azure Kubernetes Service (AKS). There is NO on-premise deployment.
- The ONLY allowed CI/CD tools are GitHub Actions (.github/workflows) and Azure DevOps Pipelines (.devops, azure-pipelines*.yml).
- Infrastructure is managed entirely with Terraform (HCL): expect .tf files, tfvars per environment, remote state on Azure Storage, and plan/apply pipelines.
- API deployment can happen either via GitHub Actions or from within the infrastructure repositories (e.g. an APIM/API definition applied by a Terraform module).
- Expected languages and technologies: Java, Scala, TypeScript, JavaScript, HCL (Terraform), Python and Bash. Identify which of these the repo actually uses.
- Common Azure building blocks: AKS, Azure API Management (APIM), Azure Storage, Application Insights / Azure Monitor.

Cover these sections (use the same headers):
1. **Stack / Project structure** — repo type (application vs infrastructure, monorepo vs single stack) and which of the PagoPA languages/technologies above it actually uses
2. **Deployment scripts** — .sh scripts, Makefile, terraform wrapper scripts (e.g. terraform.sh), real commands with usage examples
3. **CI/CD pipelines** — GitHub Actions and/or Azure DevOps only: workflow/pipeline file names, triggers, and stages (terraform plan/apply, build & push image, AKS deploy)
4. **Environment management** — environment names (e.g. dev/uat/prod, weu-dev/weu-uat/weu-prod) and how they are separated (tfvars, workspace, branch, directory)
5. **Naming conventions** — patterns for Azure resources, Terraform variables/modules, files
6. **Post-deploy monitoring** — tools actually referenced (Application Insights, Azure Monitor, Grafana, etc.)
7. **Approvals and branch protection** — CODEOWNERS, required reviewers, environment approvals, merge rules
8. **Release process** — from merge to production deploy, including whether AKS rollout / Terraform apply is manual or automatic

If a section is not inferable from the files, write a brief note saying so rather than inventing details.

--- REPOSITORY FILES ---
{files_block}

Write ONLY the markdown document, no preamble."""

        logger.info("Generating CI/CD context via LLM...")
        result = self.doc_gen._call_llm(prompt, max_tokens=6000)
        if not result:
            logger.warning(
                f"CI/CD context not generated for '{repo_full_name}': the LLM returned no "
                f"response. No file will be saved — will retry on the next invocation."
            )
            return None
        return result
