module "storage" {
  source              = "git::https://github.com/pagopa/terraform-azurerm-v4.git//IDH/storage_account"

  product_name        = var.prefix
  env                 = var.env
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.tags

  idh_resource_tier = var.idh_storage_account_resource_tier

  name   = local.project
  domain = var.domain

  embedded_subnet = {
    enabled         = true
    vnet_rg_name    = var.vnet_rg
    vnet_name       = var.vnet_name
  }

  private_dns_zone_blob_ids  = var.private_dns_zone_blob_ids
}

resource "azurerm_key_vault_secret" "connection_string" {

  name         = "storage-connection-string"
  value        = module.storage.primary_connection_string
  content_type = "text/plain"
  key_vault_id = data.azurerm_key_vault.kv.id

  tags = var.tags
}