#
# # ── Key Vault secrets ─────────────────────────────────────────────────────────
#

data "azurerm_key_vault" "kv" {
  name                = var.kv_name
  resource_group_name = var.kv_resource_group_name
}

data "azurerm_key_vault_secret" "github_token" {
  name         = "github-token"
  key_vault_id = data.azurerm_key_vault.kv.id
}

# Distinct from github-token above. That one is the classic PAT used for the
# GitHub REST API; Copilot rejects classic ghp_ tokens outright, so the LLM
# path needs a *fine-grained* PAT carrying the "Copilot Requests" ACCOUNT
# permission — which GitHub only offers when the resource owner is a personal
# account. Consequence to keep in mind operationally: this credential is tied
# to an individual's Copilot licence and expires, so it needs a named owner
# and a rotation reminder.
data "azurerm_key_vault_secret" "copilot_github_token" {
  name         = "copilot-github-token"
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

#
# # ── Monitoring ────────────────────────────────────────────────────────────────
#

data "azurerm_log_analytics_workspace" "law" {
  name                = var.log_analytics_workspace_name
  resource_group_name = var.log_analytics_workspace_resource_group_name
}

data "azurerm_application_insights" "ai" {
  name                = var.application_insights_name
  resource_group_name = var.application_insights_resource_group_name
}
