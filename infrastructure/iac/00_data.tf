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
