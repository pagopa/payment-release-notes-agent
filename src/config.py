"""Configuration management for Release Notes Agent"""

import os
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional

load_dotenv()


@dataclass
class GithubConfig:
    """GitHub API Configuration"""
    token: str = os.getenv("GITHUB_TOKEN", "")


@dataclass
class LLMConfig:
    """LLM Configuration"""
    # copilot_sdk (default), openai or anthropic.
    #
    # Two providers have been removed and must not come back:
    #   * "copilot"     — GitHub Models (models.github.ai/inference), retired on
    #                     2026-07-30; every request answers HTTP 410.
    #   * "copilot_cli" — the same Copilot agent as copilot_sdk, but reached by
    #                     spawning the npm `@github/copilot` binary. It required
    #                     a Node runtime alongside Python and paid ~7s of process
    #                     startup per call. copilot_sdk supersedes it entirely.
    # validate() rejects both by name so an old deployment fails with an
    # explanation rather than "Unsupported LLM provider".
    provider: str = os.getenv("LLM_PROVIDER", "copilot_sdk")
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    # Copilot agent (provider="copilot_sdk"). Auth resolution order:
    #   1. COPILOT_GITHUB_TOKEN — a fine-grained PAT with the "Copilot Requests"
    #      account permission (classic ghp_ tokens are NOT supported);
    #   2. the interactive `copilot` login stored on the machine — which exists
    #      on a laptop but never in a container, so validate() refuses to rely
    #      on it unless COPILOT_ALLOW_MACHINE_LOGIN is set.
    copilot_token: Optional[str] = os.getenv("COPILOT_GITHUB_TOKEN")
    copilot_model: str = os.getenv("COPILOT_MODEL", "")  # empty = Copilot default
    # Working directory handed to the agent. Kept away from the app source tree
    # so a stray tool call cannot read it. Created on demand if missing.
    copilot_workdir: str = os.getenv("COPILOT_WORKDIR", "")
    # Dump every raw LLM response (and the parse outcome) under this directory.
    # Diagnostic only — leave unset in production. See DocumentGenerator._dump_raw.
    llm_raw_dump_dir: str = os.getenv("LLM_RAW_DUMP_DIR", "")
    # Document generation settings
    environments: str = os.getenv("ENVIRONMENTS", "prod")
    document_language: str = os.getenv("DOCUMENT_LANGUAGE", "Italian")
    cicd_context_file: str = os.getenv("CICD_CONTEXT_FILE", "")  # override; auto-detect if empty


@dataclass
class AtlassianConfig:
    """Atlassian credentials — shared by JIRA and Confluence (same account on Cloud)."""
    url: str = os.getenv("ATLASSIAN_URL", "")
    user: str = os.getenv("ATLASSIAN_USER", "")
    token: str = os.getenv("ATLASSIAN_TOKEN", "")

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.user and self.token)


@dataclass
class Config:
    """Main Configuration"""
    github: GithubConfig = None
    llm: LLMConfig = None
    atlassian: AtlassianConfig = None
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    def __post_init__(self):
        if self.github is None:
            self.github = GithubConfig()
        if self.llm is None:
            self.llm = LLMConfig()
        if self.atlassian is None:
            self.atlassian = AtlassianConfig()

    def validate(self):
        """Validate configuration"""
        if not self.github.token:
            raise ValueError("GITHUB_TOKEN is required")

        _RETIRED = {
            "copilot": "it targeted GitHub Models, retired on 2026-07-30 — every "
                       "request returns HTTP 410",
            "copilot_cli": "it spawned the npm @github/copilot binary, which "
                           "required a Node runtime this image no longer ships",
        }
        if self.llm.provider in _RETIRED:
            raise ValueError(
                f"LLM_PROVIDER={self.llm.provider} has been removed: "
                f"{_RETIRED[self.llm.provider]}. Use copilot_sdk instead."
            )

        if self.llm.provider == "copilot_sdk":
            if not self.llm.copilot_token and not os.getenv("COPILOT_ALLOW_MACHINE_LOGIN"):
                # Without a token the agent silently falls back to the
                # interactive `copilot` login stored on the machine. That exists
                # on a developer laptop but never in a container, so the
                # fallback turns a missing credential into four failed sections
                # and a blank PDF. Fail at startup instead.
                raise ValueError(
                    "COPILOT_GITHUB_TOKEN is required for the copilot_sdk provider "
                    "— it must be a fine-grained PAT carrying the 'Copilot Requests' "
                    "permission (classic ghp_ tokens are rejected by Copilot). Set "
                    "COPILOT_ALLOW_MACHINE_LOGIN=1 to fall back to a local "
                    "interactive login instead."
                )
            if "/" in self.llm.copilot_model:
                # COPILOT_MODEL used to hold a GitHub Models id such as
                # "openai/gpt-4.1". Copilot model ids are unprefixed, so a
                # leftover value from an old .env or app setting would be
                # accepted by config and then rejected on the first call.
                raise ValueError(
                    f"COPILOT_MODEL={self.llm.copilot_model!r} looks like a GitHub "
                    "Models id (publisher-prefixed). Copilot model ids are "
                    "unprefixed, e.g. 'claude-sonnet-5' — leave it empty for the "
                    "Copilot default."
                )

        if self.llm.provider == "openai" and not self.llm.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI provider")
        
        if self.llm.provider == "anthropic" and not self.llm.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider")
        
        if self.atlassian.url or self.atlassian.user or self.atlassian.token:
            if not self.atlassian.enabled:
                raise ValueError("ATLASSIAN_URL, ATLASSIAN_USER e ATLASSIAN_TOKEN devono essere tutti valorizzati")


# Global config instance
config = Config()
