locals {
  project = "${var.prefix}-${var.env_short}-${var.location_short}-${var.domain}"

  kv_name                = "${local.project}-kv"
  kv_resource_group_name = "${local.project}-sec-rg"
}
