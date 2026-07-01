data "azurerm_private_dns_zone" "azurewebsite" {
  name                = var.azure_website_dns_zone_name
  resource_group_name = var.internal_dns_zone_resource_group_name
}
#
# # ── Key Vault secrets ─────────────────────────────────────────────────────────
#
data "azurerm_key_vault_secret" "github_token" {
  name         = "github-token"
  key_vault_id = data.azurerm_key_vault.kv.id
}

data "azurerm_key_vault_secret" "atlassian_token" {
  name         = "atlassian-token"
  key_vault_id = data.azurerm_key_vault.kv.id
}

data "azurerm_key_vault_secret" "atlassian_url" {
  name         = "atlassian-url"
  key_vault_id = data.azurerm_key_vault.kv.id
}

data "azurerm_key_vault_secret" "atlassian_user" {
  name         = "atlassian-user"
  key_vault_id = data.azurerm_key_vault.kv.id
}

# ── Resource group ────────────────────────────────────────────────────────────

resource "azurerm_resource_group" "rg" {
  name     = "${local.project}-rg"
  location = var.location
  tags     = var.tags
}

module "webapp" {
  # https://github.com/pagopa/terraform-azurerm-v4/releases/tag/v10.17.0
  source = "git::https://github.com/pagopa/terraform-azurerm-v4.git//IDH/app_service_webapp?ref=7787f9ec0d71db411ebab613d7731a4286210c30"

  env               = var.env
  idh_resource_tier = var.idh_app_service_resource_tier
  product_name      = var.prefix

  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location

  # App service plan
  name                  = "${local.project}-app"
  app_service_plan_name = "${local.project}-plan"

  docker_image     = "ghcr.io/pagopa/payment-release-notes-agent"
  docker_image_tag = var.docker_image_tag

  # Runtime
  always_on                    = false
  health_check_path            = "/health"
  health_check_maxpingfailures = 10

  private_endpoint_dns_zone_id = data.azurerm_private_dns_zone.azurewebsite.id
  allow_from_apim              = true
  allowed_subnet_ids           = var.allowed_subnet_ids
  allowed_service_tags         = ["AzureDevOps"]

  embedded_subnet = {
    vnet_name    = var.vnet_name
    vnet_rg_name = var.vnet_rg
    enabled      = true
  }

  app_settings = {
    # Container
    WEBSITES_PORT    = "8000"
    PYTHONUNBUFFERED = "1"

    # GitHub / LLM
    GITHUB_TOKEN  = "@Microsoft.KeyVault(SecretUri=${data.azurerm_key_vault_secret.github_token.versionless_id})"
    LLM_PROVIDER  = var.llm_provider
    COPILOT_MODEL = var.copilot_model

    # Azure Storage — async job blob + queue
    AzureWebJobsStorage = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.connection_string.versionless_id})"

    # Atlassian — optional (JIRA & Confluence export)
    ATLASSIAN_URL   = "@Microsoft.KeyVault(SecretUri=${data.azurerm_key_vault_secret.atlassian_url.versionless_id})"
    ATLASSIAN_USER  = "@Microsoft.KeyVault(SecretUri=${data.azurerm_key_vault_secret.atlassian_user.versionless_id})"
    ATLASSIAN_TOKEN = "@Microsoft.KeyVault(SecretUri=${data.azurerm_key_vault_secret.atlassian_token.versionless_id})"

    # Document generation
    ENVIRONMENTS      = var.environments
    RESPONSIBLE_TEAM  = var.responsible_team
    DOCUMENT_LANGUAGE = var.document_language
    DEPARTMENT_NAME   = var.department_name

    # Ops
    LOG_LEVEL         = var.log_level
    STALE_JOB_MINUTES = tostring(var.stale_job_minutes)
  }

  autoscale_settings = {
    max_capacity = 1
  }

  tags = var.tags
}

## ad group policy ##
resource "azurerm_key_vault_access_policy" "permissions" {
  key_vault_id = data.azurerm_key_vault.kv.id

  tenant_id = data.azurerm_key_vault.kv.tenant_id
  object_id = module.webapp.principal_id

  secret_permissions = ["Get", "List"]
}