# ── Existing network resources ────────────────────────────────────────────────

data "azurerm_subnet" "outbound" {
  name                 = var.subnet_name
  virtual_network_name = var.vnet_name
  resource_group_name  = var.vnet_resource_group_name
}

# ── Key Vault secrets ─────────────────────────────────────────────────────────

data "azurerm_key_vault_secret" "github_token" {
  name         = "github-token"
  key_vault_id = data.azurerm_key_vault.kv.id
}

data "azurerm_key_vault_secret" "storage_connection" {
  name         = "storage-connection-string"
  key_vault_id = data.azurerm_key_vault.kv.id
}

data "azurerm_key_vault_secret" "atlassian_token" {
  name         = "atlassian-token"
  key_vault_id = data.azurerm_key_vault.kv.id
}

data "azurerm_key_vault_secret" "atlassian_user" {
  name         = "atlassian-user"
  key_vault_id = data.azurerm_key_vault.kv.id
}

# ── Resource group ────────────────────────────────────────────────────────────

resource "azurerm_resource_group" "main" {
  name     = "${local.project}-rg"
  location = var.location
  tags     = var.tags
}

module "webapp" {
  source = "./.terraform/modules/__v4__/app_service"

  name                = "${local.project}-app"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location

  # App Service Plan (internal, dedicated)
  plan_type = "internal"
  plan_name = "${local.project}-plan"
  sku_name  = var.sku_name

  docker_registry_url = "https://ghcr.io"
  docker_image        = "ghcr.io/pagopa/payment-release-notes-agent"
  docker_image_tag    = var.docker_image_tag

  # Network
  public_network_access_enabled = false
  vnet_integration              = true
  subnet_id                     = data.azurerm_subnet.outbound.id
  ip_restriction_default_action = "Deny"

  # Runtime
  always_on                    = true
  health_check_path            = "/health"
  health_check_maxpingfailures = 10

  app_settings = {
    # Container
    WEBSITES_PORT    = "8000"
    PYTHONUNBUFFERED = "1"

    # GitHub / LLM
    GITHUB_TOKEN  = "@Microsoft.KeyVault(SecretUri=${data.azurerm_key_vault_secret.github_token.versionless_id})"
    LLM_PROVIDER  = var.llm_provider
    COPILOT_MODEL = var.copilot_model

    # Azure Storage — async job blob + queue
    AzureWebJobsStorage = "@Microsoft.KeyVault(SecretUri=${data.azurerm_key_vault_secret.storage_connection.versionless_id})"

    # Atlassian — optional (JIRA & Confluence export)
    ATLASSIAN_URL   = var.atlassian_url
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

  tags = var.tags
}

resource "azurerm_role_assignment" "kv_secrets_user" {
  scope                = data.azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.webapp.principal_id
}
