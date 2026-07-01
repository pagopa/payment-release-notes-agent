locals {
  project    = "${var.prefix}-${substr(var.env, 0, 1)}-${var.location_short}-${var.domain}"
  tool_name  = "payment-release-notes"
  expose_api = var.api_management_name != "" && var.api_management_rg != "" ? true : false
}
