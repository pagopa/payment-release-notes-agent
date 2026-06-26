# CI/CD Context for `pagopa/p4pa-infra`

This document describes the release and deployment process for the `pagopa/p4pa-infra` repository, including stack structure, deployment scripts, CI/CD pipelines, environment management, naming conventions, post-deploy monitoring, approvals, branch protection, and the release process.

---

## 1. Stack / Project Structure

- **Monorepo**: The repository is organized as a monorepo, containing multiple infrastructure domains and modules.
- **Directory Structure**:
  - `src/01_networking`: Networking resources.
  - `src/02_security`: Security resources.
  - `src/03_packer`: Packer images.
  - `src/04_core`: Core infrastructure.
  - `src/05_aks`: AKS clusters.
  - `src/05_monitoring`: Monitoring resources.
  - `src/05_platform`: Platform resources.
  - `src/06_domains`: Application domains (e.g., `cittadini-app`, `cittadini-common`, `cittadini-secrets`, etc.).
  - `src/07_tf_audit`: Terraform audit resources.
  - `src/tag_config`: Tag configuration.
  - `src/90_aws`: AWS-related resources.
- **Environment-specific files**: Secrets and environment variables are managed under `secret/<env>/secret.ini`.

---

## 2. Deployment Scripts

- **Terraform Management**:  
  - `scripts/terraform.sh`: Main Terraform wrapper script. **Must be run from within the exact folder modified by the PR** — this can be any stack folder under `src/`, not just `-app` folders. The script is symlinked inside each stack directory.
    - Usage — always `cd` into the specific modified folder first:
      ```bash
      cd src/06_domains/cittadini-app      # if cittadini-app was modified
      cd src/06_domains/cittadini-common   # if cittadini-common was modified
      cd src/06_domains/cittadini-secrets  # if cittadini-secrets was modified
      cd src/05_aks                        # if aks stack was modified
      ./terraform.sh plan itn-dev
      ./terraform.sh apply itn-prod
      ```
    - The folder to `cd` into is determined by which files the PR touches — each modified stack folder requires a separate `./terraform.sh` run.
    - Supported actions: `init`, `plan`, `apply`, `clean`, `list`, `help`.
    - Handles environment-specific tfvars and workspace selection automatically based on the current directory.
    - Supports resource targeting via `extract_resources` function.
- **Secrets Management**:  
  - `scripts/sops.sh`: Script for managing SOPS-encrypted secrets using Azure Key Vault.
    - Usage examples:
      - `./sops.sh d itn-dev` (decrypt)
      - `./sops.sh n itn-uat` (new file)
      - `./sops.sh a itn-prod` (add secret)
      - `./sops.sh e itn-dev` (edit secret)
      - `./sops.sh f itn-dev` (encrypt external file)
    - Loads environment variables from `secret/<env>/secret.ini`.
- **Pre-commit Checks**:
  - `scripts/pre-commit.sh`: Runs Terraform pre-commit checks via Docker.
    - Usage: `./scripts/pre-commit.sh`
    - Uses `ghcr.io/antonbabenko/pre-commit-terraform`.

---

## 3. CI/CD Pipelines

- **Tools Used**:
  - **GitHub Actions**: For static analysis, PR title validation, and release automation.
  - **Azure DevOps Pipelines**: For code review (plan) and deploy (apply) stages per domain/module.
- **GitHub Actions Workflows**:
  - `.github/workflows/static_analysis.yml`: Runs static analysis on `main` branch.
  - `.github/workflows/static_analysis_pr.yml`: Runs static analysis on all branches except `main`.
  - `.github/workflows/pr-title.yml`: Validates PR titles for semantic correctness.
  - `.github/workflows/release.yaml`: Triggers release workflow on push to `main`.
- **Azure DevOps Pipelines**:
  - Defined in `.devops/` directory:
    - Code review pipelines: e.g., `cittadini-code-review-pipelines.yml`, `core-code-review-pipelines.yml`, etc.
    - Deploy pipelines: e.g., `cittadini-deploy-pipelines.yml`, `core-deploy-pipelines.yml`, etc.
    - Base templates: `base-code-review-pipelines.yml`, `base-deploy-pipelines.yml`.
  - **Stages**:
    - **Code Review**: Runs `terraform plan` for each environment (DEV, UAT, PROD).
    - **Deploy**: Runs `terraform apply` for each environment (manual trigger).
  - **Triggers**:
    - Code review pipelines: Triggered on PRs to `main` branch.
    - Deploy pipelines: Manual only (`trigger: none`, `pr: none`).

---

## 4. Environment Management

- **Environments**:
  - `dev`, `uat`, `prod` (with region prefix, e.g., `itn-dev`, `itn-uat`, `itn-prod`)
- **Separation Mechanisms**:
  - **Terraform**: Uses environment-specific folders, tfvars, and workspaces.
  - **Azure DevOps**: Parameters per environment in pipeline YAML files.
  - **Secrets**: Managed per environment in `secret/<env>/secret.ini`.
- **Script Usage**:
  - `terraform.sh` requires the environment as argument and **must be run from within the exact folder modified by the PR** — one run per modified stack folder (e.g. `cittadini-app`, `cittadini-common`, `cittadini-secrets`, `aks-platform`, etc.).
  - `sops.sh` follows the same rule.
  - Example — if the PR touches both `cittadini-app` and `cittadini-secrets`:
    ```bash
    cd src/06_domains/cittadini-app
    ./terraform.sh plan itn-dev

    cd ../cittadini-secrets
    ./terraform.sh plan itn-dev
    ```

---

## 5. Naming Conventions

- **Resource Naming**:
  - Environment folders: `<region>-<env>` (e.g., `itn-dev`)
  - Domain names: Used as parameters (e.g., `cittadini`, `core`, `monitoring`, `networking`)
  - Working directories: `src/06_domains/<domain>-app`, `src/06_domains/<domain>-common`, `src/06_domains/<domain>-secrets`
- **File Naming**:
  - Pipeline files: `<domain>-code-review-pipelines.yml`, `<domain>-deploy-pipelines.yml`
  - Base templates: `base-code-review-pipelines.yml`, `base-deploy-pipelines.yml`
  - Scripts: `terraform.sh`, `sops.sh`, `pre-commit.sh`
- **Variables**:
  - Azure DevOps pipeline parameters: `SC_PLAN_NAME`, `SC_APPLY_NAME`, `POOL_NAME`, `AKS_NAME`, etc.
  - Secret variables: `kv_name`, `kv_sops_key_name`, `file_crypted` in `secret.ini`.

---

## 6. Post-deploy Monitoring

- **Monitoring Infrastructure**:
  - Dedicated module: `src/05_monitoring`
  - Monitoring deployments managed via Azure DevOps pipelines.
- **Tools**:
  - Not explicitly mentioned in the files.  
  - **Note**: Actual monitoring tools (e.g., Application Insights, Datadog, Grafana) are not specified in the provided files.

---

## 7. Approvals and Branch Protection

- **CODEOWNERS**:
  - `CODEOWNERS` file specifies:
    - `* @pagopa/payments-cloud-admin @pagopa/p4pa-admins`
    - All files require review from these teams.
- **Branch Protection**:
  - PR title validation enforced via `.github/workflows/pr-title.yml` (semantic PR titles).
  - Static analysis checks enforced on PRs and pushes.
- **Required Reviewers**:
  - As per `CODEOWNERS`, PRs require approval from designated admin teams.

---

## 8. Release Process

- **Release Automation**:
  - **GitHub Actions**:
    - `.github/workflows/release.yaml`: Runs on push to `main` branch (excluding markdown, dotfiles, and `CODEOWNERS`).
    - Uses `pagopa/eng-github-actions-iac-template/global/release-action@main`.
    - Release notes generated via `.releaserc.json` (semantic-release).
  - **Azure DevOps Deploy Pipelines**:
    - Manual trigger required for deploy pipelines (`trigger: none`, `pr: none`).
    - Separate deploy pipelines for each domain/module and environment.
- **Process Flow**:
  1. PR is opened, triggering code review pipelines and static analysis.
  2. PR title is validated for semantic correctness.
  3. PR is reviewed and approved by CODEOWNERS.
  4. PR is merged to `main`.
  5. Release workflow runs automatically (GitHub Actions).
  6. Manual deployment is performed via Azure DevOps deploy pipelines for DEV, UAT, and PROD environments.
- **Manual/Automatic Steps**:
  - Code review and release are automated.
  - Deployments to environments are manual via Azure DevOps.

---

**If further details are required (e.g., monitoring tools, resource naming specifics), please refer to the respective module documentation or contact repository maintainers.**