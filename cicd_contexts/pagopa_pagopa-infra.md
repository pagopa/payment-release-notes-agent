# CI/CD Context — pagopa/pagopa-infra

This file describes the deployment process for the `pagopa/pagopa-infra` repository.
It is automatically injected into LLM prompts to generate accurate, repository-specific documentation.

---

## Terraform Stack Structure

Each product domain is split into three sub-stacks:
- `*-common/` — shared resources (DB, storage, service bus, shared Key Vault secrets)
- `*-app/` — application resources (App Service, Function App, Container App, AKS workloads)
- `*-secrets/` or `*-secret/` — domain-specific Key Vault secrets

Cross-cutting infrastructure stacks:
- `src/next-core/` — APIM, AppGateway, Redis, DNS, VPN (main stack)
- `src/core/` — legacy equivalent of next-core
- `src/network/`, `src/network-secrets/`
- `src/cloudo/` — PagoPA internal monitoring platform

---

## Main Deployment Script: `terraform.sh`

Each stack contains a symlink `terraform.sh → ../../../scripts/terraform.sh` (version 3.0).

**Usage:**
```bash
cd src/domains/<domain>-common
./terraform.sh plan weu-dev
./terraform.sh apply weu-dev
```

**Available environments** (subdirectories of `env/`):
- West Europe: `weu-dev`, `weu-uat`, `weu-prod`
- Italy North: `itn-dev`, `itn-uat`, `itn-prod`
- Legacy (some stacks): `dev`, `uat`, `prod`

**Available actions:**
- `init` — initialises the backend with `-backend-config=./env/$env/backend.tfvars`
- `plan` — runs `terraform plan -var-file=./env/$env/terraform.tfvars`
- `apply` — runs `terraform apply` after plan
- `summ` — generates a human-readable plan summary using `tf-summarize`
- `clean` — removes `.terraform/` and plan files

**Production behaviour (`*prod` environments):**
- `-auto-approve` is blocked
- The plan is saved as a `.tfplan` file with timestamp
- If `.terraform-opa` is present: evaluates OPA policies, shows compliance score, requires explicit confirmation
- Requires manual confirmation by typing `"yes"` before apply
- **Pre-apply audit**: writes a record to Azure Table Storage (`tfauditprodpagopa` / `prodapply`) with branch, commit hash, user, folder
- **Post-apply audit**: uploads `.plan` and `.apply` files to Azure Blob (`prod-apply` container)

---

## CI/CD Pipelines: Azure DevOps (`.devops/`)

Deployments are **not** automatic on merge. They are manual pipelines on Azure DevOps.

### Per-domain pipelines
Each domain has two files:
- `<domain>-code-review-pipelines.yml` — triggers automatically on PRs to `main`; runs `terraform plan` only (no apply)
- `<domain>-deploy-pipelines.yml` — manual trigger (`trigger: none`, `pr: none`); runs `terraform plan` then `terraform apply`

### Deploy pipeline parameters
```yaml
parameters:
  - name: DEV    # boolean, default: True
  - name: UAT    # boolean, default: True
  - name: PROD   # boolean, default: True
```
Each environment can be individually included or excluded at run time.

### Service connections per environment
- Plan: `$(TF_AZURE_SERVICE_CONNECTION_PLAN_NAME_DEV/UAT/PROD)`
- Apply: `$(TF_AZURE_SERVICE_CONNECTION_APPLY_NAME_DEV/UAT/PROD)`
- Agent pool: `$(TF_POOL_NAME_DEV/UAT/PROD)`

### External template
Pipelines use `pagopa/azure-pipeline-templates` at tag `v6.9.0`, which internally runs `terraform init`, `plan`, and `apply`.

### Timeout
15 minutes per stack (some legacy stacks: 10 minutes).

---

## GitHub Actions (`.github/workflows/`)

Not used for deployments. Used for:
- `static_analysis_pr.yml` — on push to non-main branches: runs `terraform fmt`, `terraform_docs`, `terraform_validate` on modified folders
- `pr-title.yml` — validates that the PR title follows conventional commit format (`fix|feat|refactor|docs|chore|breaking`)
- `main.yml` — auto-assigns the PR author
- `release.yml` — creates a semantic release on push to main

---

## Environment Management

**No Terraform workspaces.** Environments are separated by distinct backends and tfvars files.

Each stack contains `env/<env>/`:
- `backend.ini` — single line: `subscription=<DEV-pagoPA|UAT-pagoPA|PROD-pagoPA>`
- `backend.tfvars` — remote state coordinates (storage account, container, key)
- `terraform.tfvars` — variable values for that environment

**Backend storage accounts:**
| Environment | Storage Account | Container |
|---|---|---|
| dev (WEU domains) | `pagopainfraterraformdev` | `azurermstate` |
| prod (WEU domains) | `pagopainfraterraformprod` | `azurermstate` |
| dev (next-core/itn) | `tfinfdevpagopa` | `terraform-state` |
| prod (next-core/itn) | `tfinfprodpagopa` | `terraform-state` |

---

## Terraform Modules

All modules are pinned by **Git commit hash** (not semver tags).

```hcl
module "__v4__" {
  source = "git::https://github.com/pagopa/terraform-azurerm-v4?ref=<commit-hash>"
  # vX.Y.Z
}
```

**Two generations in use simultaneously:**
- `terraform-azurerm-v3` — legacy stacks
- `terraform-azurerm-v4` — current stacks (preferred)

**Pinned Terraform version:** `1.9.8` (`.terraform-version` file)

**Main providers:**
- `hashicorp/azurerm ~> 4.16` (v4 stacks) or `<= 3.116.0` (v3/legacy)
- `hashicorp/azuread ~> 3.1`
- `azure/azapi <= 1.3.0`
- `cyrilgdn/postgresql ~> 1.26.0`

---

## Naming Conventions

```
project = "pagopa-<env_short>-<location_short>-<domain>"
product = "pagopa-<env_short>"
```

**Environment codes:** `d` (dev), `u` (uat), `p` (prod)
**Location codes:** `weu` (West Europe), `itn` (Italy North)

**Resource Group pattern:** `pagopa-<env_short>-<scope>-rg`
**Application Insights:** `pagopa-<env_short>-appinsights`
**Log Analytics:** `pagopa-<env_short>-law` (WEU) / `pagopa-<env_short>-itn-core-law` (ITN)
**APIM:** `pagopa-<env_short>-apim`
**Key Vault secrets:** lowercase kebab-case

---

## Post-Deploy Monitoring

| Tool | Usage |
|---|---|
| **Azure Application Insights** | Application telemetry; `pagopa-<env_short>-appinsights` |
| **Azure Monitor / Log Analytics** | Centralised logs; action groups for alerting |
| **ClouDO** | PagoPA internal monitoring platform; Terraform-managed in `src/cloudo/`; integrates App Insights + Slack + Opsgenie; approval runbook with 120-min TTL |
| **Slack** | Real-time alerts on `#cloudo-pagopa-<env>` |
| **Opsgenie / JSM** | Production incident management; enabled only if `env_short == "p"` |
| **Grafana** | Azure Managed Grafana with auto-dashboards |
| **Synthetic Monitoring** | Dedicated stack `src/synthetic-monitoring/` with Azure Monitor |

---

## Approvals and CODEOWNERS

```
# Default: all paths
* @pagopa/pagopa-team-core @pagopa/pagopa-team-touchpoint @pagopa/payments-cloud-admin

# Specific paths
/src/next-core                 @pagopa/payments-cloud-admin
/src/network                   @pagopa/payments-cloud-admin
/src/db-security               @pagopa/payments-cloud-admin
/src/domains/selfcare-*        @pagopa/infrastructure-admins @pagopa/pagopa-team-core ...
```

**Branch protection on `main`:**
- Minimum 1 approving reviewer required
- Code owner review mandatory
- Dismiss stale reviews on new pushes
- Last-push approval required (the person who made the last push cannot self-approve)
- Linear history (squash or rebase, no merge commits)
- Force push blocked

---

## Release Process

1. PR opened → `static_analysis_pr.yml` validates fmt/validate on modified files
2. PR approved by at least 1 code owner → merge to `main` (squash/rebase)
3. `release.yml` automatically generates a GitHub Release with semantic versioning
4. **Manual** execution of the deploy pipeline on Azure DevOps for each modified stack
5. Deployment sequence: **DEV → UAT → PROD** (with verification between environments)
6. In PROD: OPA policy check + manual confirmation + audit log on Azure Storage

---

## Pre-commit Hooks (run locally and in CI)

- `terraform_fmt` — formatting
- `terraform_docs` — generates `README.md` in each stack
- `terraform_validate` — validation with readonly lockfile
- `check-variables-tf.sh` — PagoPA variable naming convention
- `check-env-vars-consistency.sh` — verifies that all tfvars define the same variables across all environments
- `check-unused-vars` — unused Terraform variables