# CI/CD Context — pagopa/pagopa-infra

## Stack
- Infrastructure-only repo — Terraform, Azure provider, pinned version `1.9.8`
- Multi-region: **WEU** (West Europe) and **ITN** (Italy North)
- Compute: AKS clusters in both regions; cross-product services in `src/core/` and `src/next-core/`
- Each domain is split into three stacks: `*-app/`, `*-common/`, `*-secret/`

## Environments
| Code | Region |
|---|---|
| `weu-dev` / `itn-dev` | Development |
| `weu-uat` / `itn-uat` | UAT |
| `weu-prod` / `itn-prod` | Production |

No Terraform workspaces — environments are separated by `env/<env>/backend.tfvars` and `terraform.tfvars`.

## Deploy — `terraform.sh`
```bash
cd src/domains/<domain>-app
./terraform.sh plan weu-dev
./terraform.sh apply weu-dev
```
Actions: `init`, `plan`, `apply`, `summ`, `clean`.

**Production (`*-prod`):**
- `-auto-approve` blocked — manual `"yes"` required
- OPA policy check before apply
- Pre-apply audit record → Azure Table Storage (`tfauditprodpagopa`)
- Post-apply artifacts uploaded → Azure Blob (`prod-apply` container)

## Pipeline — Azure DevOps (`.devops/`)
- **Code review pipeline** (`<domain>-code-review-pipelines.yml`): auto-triggered on PR, runs `terraform plan` only
- **Deploy pipeline** (`<domain>-deploy-pipelines.yml`): manual trigger, runs plan then apply; parameters `DEV/UAT/PROD` (boolean) to select environments
- Template: `pagopa/azure-pipeline-templates@v6.9.0`
- Timeout: 15 min per stack

## Monitoring post-deploy
- **Application Insights**: `pagopa-<env_short>-appinsights`
- **Log Analytics**: `pagopa-<env_short>-law` (WEU) / `pagopa-<env_short>-itn-core-law` (ITN)
- **ClouDO**: PagoPA internal platform — Slack (`#cloudo-pagopa-<env>`) + Opsgenie (prod only)
- **Grafana**: Azure Managed Grafana with auto-dashboards

## Release process
1. PR → code review pipeline runs `terraform plan` automatically
2. Approved by code owner → merge to `main`
3. Manual execution of deploy pipeline on Azure DevOps per modified stack
4. Sequence: **DEV → UAT → PROD**
5. PROD: OPA check + manual confirmation + audit log
