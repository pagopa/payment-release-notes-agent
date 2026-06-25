# CI/CD Context — `pagopa/p4pa-infra`

This file describes the deployment process for the `pagopa/p4pa-infra` repository.
It is automatically injected into LLM prompts to generate accurate, repository-specific documentation.

---

## 1. Stack / Project Structure

The `pagopa/p4pa-infra` repository is organised as a **monorepo** for Terraform infrastructure management. Main directory structure:

- `src/01_networking`, `src/02_security`, `src/03_packer`, `src/04_core`, `src/05_aks`, `src/05_monitoring`, `src/05_platform`, `src/06_domains`, `src/07_tf_audit`, `src/90_aws`, `src/tag_config` — each folder represents an infrastructure domain or specific component.
- `src/06_domains` contains subdirectories for application domains (e.g. `cittadini-app`, `cittadini-common`, `cittadini-secrets`).
- Pipelines are defined in `.devops/`, split by domain and type (`*-code-review-pipelines.yml`, `*-deploy-pipelines.yml`).
- Utility scripts are in `scripts/`.

---

## 2. Deployment Scripts

### `scripts/terraform.sh`

Terraform orchestration script for running the main actions (`init`, `plan`, `apply`, `destroy`, etc.) on a specific environment.

```bash
./scripts/terraform.sh plan itn-dev
./scripts/terraform.sh apply itn-uat
./scripts/terraform.sh destroy itn-prod
```

Also supports: `clean` (remove local state), `list` (list available environments), and other utilities.

### `scripts/sops.sh`

Script for managing encrypted secret files via SOPS and Azure Key Vault.

```bash
./scripts/sops.sh d itn-dev    # Decrypt secret file for itn-dev
./scripts/sops.sh n itn-uat    # Create a new encrypted template for itn-uat
./scripts/sops.sh a itn-prod   # Add a new secret to itn-prod
```

Loads environment variables from `./secret/<env>/secret.ini`.

### `scripts/pre-commit.sh`

Runs Terraform pre-commit checks via Docker container.

```bash
./scripts/pre-commit.sh
```

Uses the `ghcr.io/antonbabenko/pre-commit-terraform` image.

---

## 3. CI/CD Pipelines

### Tools

- **Azure DevOps Pipelines**: YAML pipelines in `.devops/` for code review (plan) and deploy (apply).
- **GitHub Actions**: workflows in `.github/workflows/` for static analysis, PR validation, and releases.

### Azure DevOps Pipelines

- **Code Review Pipelines** (`*-code-review-pipelines.yml`): run `terraform plan` on selected domains and environments — triggered automatically on PR.
- **Deploy Pipelines** (`*-deploy-pipelines.yml`): run `terraform apply` manually on enabled environments (`trigger: none`).

Pipelines are parameterised by environment (`DEV`, `UAT`, `PROD`) and domain, using shared templates (`base-code-review-pipelines.yml`, `base-deploy-pipelines.yml`).

Example stage in `.devops/cittadini-code-review-pipelines.yml`:

```yaml
- template: './base-code-review-pipelines.yml'
  parameters:
    ENV: "dev"
    WORKING_DIR_APP: "src/06_domains/cittadini-app"
```

### GitHub Actions Workflows

- **Static Analysis** (`static_analysis.yml`, `static_analysis_pr.yml`): runs Terraform static analysis via the `pagopa/eng-github-actions-iac-template/azure/terraform-static-analysis` action.
- **Release** (`release.yaml`): publishes a GitHub Release on push to `main`.
- **PR Title Check** (`pr-title.yml`): validates that the PR title follows semantic commit conventions.

---

## 4. Environment Management

Main environments:

- **dev** (`itn-dev`)
- **uat** (`itn-uat`)
- **prod** (`itn-prod`)

Environment separation is achieved via:

- Pipeline parameters (`ENV: dev|uat|prod`)
- Variable and secret directories (`./env/<env>`, `./secret/<env>/secret.ini`)
- Terraform variables (e.g. `TF_ENVIRONMENT_FOLDER: itn-dev`)
- Dedicated service connections and agent pools per environment (e.g. `TF_AZURE_SERVICE_CONNECTION_PLAN_NAME_DEV`)

---

## 5. Naming Conventions

- **Files and directories**:
  - Domains follow `src/<number>_<domain>`, e.g. `src/01_networking`, `src/06_domains/cittadini-app`.
  - Pipeline files follow `<domain>-code-review-pipelines.yml` and `<domain>-deploy-pipelines.yml`.
- **Environment variables**:
  - Prefixed with `TF_` for service connection and pool variables, e.g. `TF_AZURE_SERVICE_CONNECTION_PLAN_NAME_DEV`.
- **Releases**:
  - Semantic release with `angular` preset and custom rules for breaking changes.

---

## 6. Post-Deploy Monitoring

A dedicated `src/05_monitoring` domain exists for monitoring infrastructure. Specific tooling details should be referenced from the internal monitoring domain documentation or its Terraform modules.

---

## 7. Approvals and Branch Protection

- **CODEOWNERS**: All files are owned by `@pagopa/payments-cloud-admin` and `@pagopa/p4pa-admins`.
- **Required reviewers**: At least one CODEOWNERS group must approve PRs.
- **Merge rules**:
  - PR title validated by `pr-title.yml` workflow (semantic commit format).
  - Mandatory static analysis on every PR via dedicated workflows.

---

## 8. Release Process

1. **PR opened**: static analysis and PR title validation via GitHub Actions; code review pipeline (Terraform plan) on Azure DevOps for all enabled environments.
2. **PR approved**: mandatory approval from CODEOWNERS.
3. **Merge to `main`**: `release.yaml` automatically publishes a GitHub Release via semantic-release; static analysis runs on `main`.
4. **Deploy**: deploy pipelines (`*-deploy-pipelines.yml`) are **manual** (`trigger: none`), launched from Azure DevOps by authorised operators only. Pipeline parameters allow selecting the target environment and domain.
5. **Post-deploy**: no automated post-deploy verification steps are defined in the current pipeline configuration.
