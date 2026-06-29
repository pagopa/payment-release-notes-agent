data "azurerm_key_vault" "kv" {
  name                = local.kv_name
  resource_group_name = local.kv_resource_group_name
}
