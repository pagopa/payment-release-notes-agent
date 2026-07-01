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
    api_base_url: str = os.getenv("GITHUB_API_BASE_URL", "https://api.github.com")


@dataclass
class LLMConfig:
    """LLM Configuration"""
    provider: str = os.getenv("LLM_PROVIDER", "copilot")  # copilot, openai or anthropic
    github_token: Optional[str] = os.getenv("GITHUB_TOKEN")  # For GitHub Copilot
    copilot_model: str = os.getenv("COPILOT_MODEL", "openai/gpt-4.1")
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    # Document generation settings
    environments: str = os.getenv("ENVIRONMENTS", "dev,uat,prod")
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
class PDFConfig:
    """PDF Export Configuration"""
    enabled: bool = os.getenv("GENERATE_PDF", "true").lower() == "true"
    output_path: str = os.getenv("PDF_OUTPUT_PATH", "./output/release_notes.pdf")
    template: str = "default"


@dataclass
class ReleaseConfig:
    """Release Notes Configuration"""
    version: str = os.getenv("RELEASE_VERSION", "1.0.0")
    release_date: Optional[str] = os.getenv("RELEASE_DATE")
    include_contributors: bool = os.getenv("INCLUDE_CONTRIBUTORS", "true").lower() == "true"
    include_commits: bool = os.getenv("INCLUDE_COMMITS", "true").lower() == "true"


@dataclass
class Config:
    """Main Configuration"""
    github: GithubConfig = None
    llm: LLMConfig = None
    atlassian: AtlassianConfig = None
    pdf: PDFConfig = None
    release: ReleaseConfig = None
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    def __post_init__(self):
        if self.github is None:
            self.github = GithubConfig()
        if self.llm is None:
            self.llm = LLMConfig()
        if self.atlassian is None:
            self.atlassian = AtlassianConfig()
        if self.pdf is None:
            self.pdf = PDFConfig()
        if self.release is None:
            self.release = ReleaseConfig()

    def validate(self):
        """Validate configuration"""
        if not self.github.token:
            raise ValueError("GITHUB_TOKEN is required")
        
        if self.llm.provider == "copilot" and not self.llm.github_token:
            raise ValueError("GITHUB_TOKEN is required for Copilot provider")
        
        if self.llm.provider == "openai" and not self.llm.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI provider")
        
        if self.llm.provider == "anthropic" and not self.llm.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider")
        
        if self.atlassian.url or self.atlassian.user or self.atlassian.token:
            if not self.atlassian.enabled:
                raise ValueError("ATLASSIAN_URL, ATLASSIAN_USER e ATLASSIAN_TOKEN devono essere tutti valorizzati")


# Global config instance
config = Config()
