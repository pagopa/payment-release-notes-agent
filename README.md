# Release Notes Agent

Generates professional release documentation from GitHub Pull Requests, using LLMs to analyse changes and produce structured content. Outputs formatted PDFs, native Confluence pages, and JIRA attachments.

## Features

- Automatic analysis of commits, changed files, and PR metadata
- LLM-generated sections: executive summary, technical analysis, deployment plan, risk matrix, post-deploy verification
- PDF export with professional formatting (bold, inline code, code blocks, tables)
- Native Confluence page in Storage Format (headings, tables, coloured status macros)
- PDF attachment on JIRA tickets with automatic comment
- Multi-provider LLM support: GitHub Models (Copilot), OpenAI, Anthropic

## Architecture

```
release-notes-agent/
├── src/
│   ├── agent/
│   │   ├── enhanced_release_notes_agent.py   # Main orchestrator
│   │   ├── release_notes_agent.py            # Base agent (simple PDF only)
│   │   ├── tools/
│   │   │   ├── github_tools.py               # Fetch PR data from GitHub API
│   │   │   ├── analysis_tools.py             # LLM-based change categorisation
│   │   │   ├── document_generator.py         # LLM section generation
│   │   │   └── repo_analyzer.py              # Repo analysis to generate cicd_context
│   │   └── exporters/
│   │       ├── enhanced_pdf_exporter.py      # Structured PDF (ReportLab)
│   │       ├── confluence_exporter.py        # Confluence Storage Format page
│   │       ├── jira_exporter.py              # Attachment + comment on JIRA ticket
│   │       └── pdf_exporter.py              # Base PDF (used by base agent)
│   ├── models/release_notes.py               # Core data model
│   ├── config.py                             # Configuration from env vars
│   └── cli.py                               # CLI (click)
├── infrastructure/
│   └── local_server.py                       # FastAPI server — local dev and production
├── cicd_contexts/                            # CI/CD context files for supported repositories
├── Dockerfile                               # Multi-stage: local (port 7071) + production (port 8000)
├── docker-compose.yml                        # Local startup
└── generate_release.sh                      # End-to-end bash script
```

## CI/CD Contexts

The tool requires a context file for each supported repository. The file describes the team's pipelines, environments, and tooling, and is injected into LLM prompts to generate specific deployment steps.

```
cicd_contexts/
└── owner_repo.md     # e.g. pagopa_pagopa-infra.md
```

**Context files must be written in English.** The LLM prompts are in English, and keeping the context in the same language improves the quality and precision of the generated output. The document language (e.g. Italian) is controlled separately via `DOCUMENT_LANGUAGE`.

A context file should cover:
- Stack and directory structure
- Deployment scripts and their usage
- CI/CD pipeline types (code review vs deploy, manual vs automatic)
- Available environments and how they are separated
- Naming conventions
- Approvals, CODEOWNERS, and branch protection rules
- Post-deploy monitoring tools

To automatically generate a context for a new repository:

```bash
python main.py analyze-repo https://github.com/owner/repo
```

If documentation is requested for a repository with no context file, the tool returns an error.

## Configuration

Copy `.env.example` to `.env` and fill in the variables:

```bash
# GitHub
GITHUB_TOKEN=ghp_...

# LLM — choose one provider
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-...

# LLM_PROVIDER=copilot
# COPILOT_MODEL=openai/gpt-4.1

# Azure Storage — required for the async job pattern
AzureWebJobsStorage=DefaultEndpointsProtocol=https;AccountName=...

# Atlassian — shared credentials for JIRA and Confluence
ATLASSIAN_URL=https://your-org.atlassian.net
ATLASSIAN_USER=email@company.com
ATLASSIAN_TOKEN=<token from id.atlassian.com/manage-profile/security/api-tokens>

# Document
ENVIRONMENTS=dev,uat,prod
RESPONSIBLE_TEAM=Team Infrastructure
DOCUMENT_LANGUAGE=Italian
DEPARTMENT_NAME=Payments Department
```

## Local Development

```bash
docker compose up --build
```

The FastAPI server is available at `http://localhost:7071`.

### Generating a document

The API is asynchronous: `POST /api/generate` returns a `job_id` immediately, then poll `GET /api/status/{job_id}` until the job completes.

```bash
# Start generation — returns job_id
curl -X POST http://localhost:7071/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "pagopa/pagopa-infra",
    "pr_number": 3924,
    "version": "1.2.0"
  }'

# Poll until completed
curl http://localhost:7071/api/status/<job_id>

# With JIRA attachment and Confluence page
curl -X POST http://localhost:7071/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "pagopa/pagopa-infra",
    "pr_number": 3924,
    "version": "1.2.0",
    "jira_issue_key": "PROJ-123",
    "confluence_space": "TECH",
    "confluence_parent_page": "1590690001",
    "confluence_page_title": "Deploy pagopa-infra v1.2.0"
  }'
```

Request fields:

| Field | Required | Description |
|-------|----------|-------------|
| `platform` | ✅ | GitHub `owner/repo` |
| `pr_number` | ✅ | Pull Request number |
| `version` | No | Release version (default: `1.0.0`) |
| `jira_issue_key` | No | JIRA ticket key (e.g. `PROJ-123`) |
| `confluence_space` | No | Confluence space key (e.g. `TECH`) |
| `confluence_parent_page` | No | Title or numeric ID of the parent page |
| `confluence_page_title` | No | Title of the page to create |

## Deploying to Azure

The service runs as an **Azure App Service Web App for Containers** on a B1 dedicated plan. The same FastAPI server (`infrastructure/local_server.py`) is used for both local development and production.

### Build and push image

```bash
docker buildx build --platform linux/amd64 --target production \
  -t ghcr.io/pagopa/payment-release-notes-agent:<tag> --push .
```

The GitHub Actions workflows handle this automatically:
- `.github/workflows/docker-build.yml` — builds and pushes on every PR (tagged `sha-*` and `pr-*`)
- `.github/workflows/release.yml` — builds and pushes the versioned image (`vX.X.X`) on merge to `main`, then creates the GitHub Release and git tag

### App Service configuration

| App Setting | Value |
|-------------|-------|
| `WEBSITES_PORT` | `8000` |
| `GITHUB_TOKEN` | GitHub PAT |
| `AzureWebJobsStorage` | Storage Account connection string |
| `LLM_PROVIDER` | `copilot` |
| `COPILOT_MODEL` | `openai/gpt-4.1` |

See [Environment Variables](#environment-variables) for the full list.

### End-to-end script

```bash
# Generate, poll, and download the PDF
./generate_release.sh pagopa/pagopa-infra 3924 1.2.0

# With JIRA and Confluence
CONFLUENCE_SPACE=TECH \
CONFLUENCE_PARENT=1590690001 \
CONFLUENCE_TITLE="Deploy v1.2.0" \
./generate_release.sh pagopa/pagopa-infra 3924 1.2.0 PROJ-123

# With APIM subscription key
API_KEY=xxx ./generate_release.sh pagopa/pagopa-infra 3924 1.2.0
```

### API

- `POST /api/generate` — starts generation, responds `202` with `job_id`
- `GET  /api/status/{job_id}` — polling: `pending` → `completed` (with `download_url`) or `failed`
- `GET  /health` — health check

The completed PDF is available via SAS URL for 1 hour.

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub PAT (API access + GitHub Models if using copilot) |
| `AzureWebJobsStorage` | Azure Storage Account connection string (blob job state) |
| `LLM_PROVIDER` | `openai` / `anthropic` / `copilot` |

### LLM — set only for the provider in use

| Variable | Description |
|----------|-------------|
| `COPILOT_MODEL` | GitHub Models model ID (e.g. `openai/chatgpt-4.1`) |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | OpenAI model ID (default: `gpt-4o`) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ANTHROPIC_MODEL` | Anthropic model ID (default: `claude-sonnet-4-6`) |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBSITES_PORT` | — | `8000` — required on Azure App Service |
| `ATLASSIAN_URL` | — | Atlassian base URL (JIRA + Confluence) |
| `ATLASSIAN_USER` | — | Atlassian account email |
| `ATLASSIAN_TOKEN` | — | Atlassian API token |
| `ENVIRONMENTS` | `dev,uat,prod` | Deployment environments |
| `RESPONSIBLE_TEAM` | `Team Infrastructure` | Team name in deployment steps |
| `DOCUMENT_LANGUAGE` | `Italian` | Language for generated content |
| `DEPARTMENT_NAME` | — | Department name in the PDF header |
| `STALE_JOB_MINUTES` | `20` | Minutes before a pending job is marked as failed |
| `LOG_LEVEL` | `INFO` | Python logging level |

## CLI

```bash
# Generate with enhanced agent (structured PDF)
python main.py generate https://github.com/owner/repo/pull/123 --version 1.2.0 --enhanced

# Preview without export
python main.py preview https://github.com/owner/repo/pull/123 --enhanced

# Analyse a repository and generate its cicd_context
python main.py analyze-repo https://github.com/owner/repo

# List available models on GitHub Models
python main.py list-models
```

---

**Made with ❤️ by [@payments-cloud-admin](https://github.com/orgs/pagopa/teams/payments-cloud-admin)**
