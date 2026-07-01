module "apim_api_payment_release_notes_v1" {
  # https://github.com/pagopa/terraform-azurerm-v4/releases/tag/v10.17.0
  source = "git::https://github.com/pagopa/terraform-azurerm-v4.git//api_management_api?ref=7787f9ec0d71db411ebab613d7731a4286210c30"
  count  = local.expose_api ? 1 : 0

  name                = "${var.prefix}-${local.tool_name}-api"
  api_management_name = var.api_management_name
  resource_group_name = var.api_management_rg
  api_version         = "v1"

  product_ids = ["${var.prefix}-${local.tool_name}-product"]

  display_name = "Payment Release Notes API"
  description  = "Async release notes generation from GitHub Pull Requests"

  path      = var.api_path
  protocols = ["https"]

  service_url = "https://${module.webapp.default_site_hostname}/api"

  content_format = "openapi"
  content_value = templatefile("${path.module}/api/v1/_openapi.json.tpl", {
    host     = var.apim_hostname
    api_path = local.tool_name
  })

  xml_content = templatefile("${path.module}/api/v1/_base_policy.xml", {
    backend_base_url = "https://${module.webapp.default_site_hostname}/api"
  })

  subscription_required = true

  version_set_id = azurerm_api_management_api_version_set.payment_release_notes[0].id

  depends_on = [azurerm_api_management_product.payment_release_notes]
}

resource "azurerm_api_management_api_version_set" "payment_release_notes" {
  count = local.expose_api ? 1 : 0

  name                = "${var.prefix}-${local.tool_name}-version-set"
  resource_group_name = var.api_management_rg
  api_management_name = var.api_management_name
  display_name        = "Payment Release Notes API"
  versioning_scheme   = "Segment"
}

resource "azurerm_api_management_product" "payment_release_notes" {
  count = local.expose_api ? 1 : 0

  resource_group_name   = var.api_management_rg
  api_management_name   = var.api_management_name
  product_id            = "${var.prefix}-${local.tool_name}-product"
  display_name          = "Payment Release Notes"
  description           = "B2B API product for the Payment Release Notes Agent"
  subscription_required = true
  approval_required     = false
  published             = true
}

resource "azurerm_api_management_subscription" "payment_release_notes" {
  count = local.expose_api ? 1 : 0

  resource_group_name = var.api_management_rg
  api_management_name = var.api_management_name
  product_id          = azurerm_api_management_product.payment_release_notes[0].id
  display_name        = "${var.prefix}-${local.tool_name}-subscription"
  state               = "active"
  allow_tracing       = false
}

resource "azurerm_key_vault_secret" "apim_subscription_key" {
  count = local.expose_api ? 1 : 0

  name         = "${local.project}-apim-subkey"
  value        = azurerm_api_management_subscription.payment_release_notes[0].primary_key
  key_vault_id = data.azurerm_key_vault.kv.id
}
