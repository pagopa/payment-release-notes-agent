module "apim_api_payment_release_notes_v1" {
  # https://github.com/pagopa/terraform-azurerm-v4/releases/tag/v10.17.0
  source = "git::https://github.com/pagopa/terraform-azurerm-v4.git//api_management_api?ref=7787f9ec0d71db411ebab613d7731a4286210c30"
  count  = var.api_management_name != "" && var.api_management_rg != "" ? 1 : 0

  name                = "${var.prefix}-payment-release-notes-api"
  api_management_name = var.api_management_name
  resource_group_name = var.api_management_rg
  api_version         = "v1"

  product_ids = [azurerm_api_management_product.payment_release_notes.id]

  display_name = "Payment Release Notes API"
  description  = "REST API for the Payment Release Notes Agent — async release notes generation from GitHub PRs"

  path      = var.api_path
  protocols = ["https"]

  service_url = "https://${module.webapp.default_site_hostname}/api"

  content_format = "openapi"
  content_value = templatefile("${path.module}/api/v1/_openapi.json.tpl", {
    host     = var.api_manager_hostname
    api_path = var.api_path
  })

  xml_content = templatefile("${path.module}/api/v1/_base_policy.xml", {
    backend_base_url = "https://${module.webapp.default_site_hostname}/api"
  })

  subscription_required = true

  version_set_id = azurerm_api_management_api_version_set.payment_release_notes[0].id

  depends_on = [azurerm_api_management_product.payment_release_notes]
}

resource "azurerm_api_management_api_version_set" "payment_release_notes" {
  count = var.api_management_name != "" && var.api_management_rg != "" ? 1 : 0

  name                = "${var.prefix}-payment-release-notes-version-set"
  resource_group_name = var.api_management_rg
  api_management_name = var.api_management_name
  display_name        = "Payment Release Notes API"
  versioning_scheme   = "Segment"
}

resource "azurerm_api_management_product" "payment_release_notes" {
  count = var.api_management_name != "" && var.api_management_rg != "" ? 1 : 0

  resource_group_name   = var.api_management_rg
  api_management_name   = var.api_management_name
  product_id            = "${var.prefix}-payment-release-notes-product"
  display_name          = "Payment Release Notes"
  description           = "B2B API product for the Payment Release Notes Agent"
  subscription_required = true
  approval_required     = false
  published             = true
}
