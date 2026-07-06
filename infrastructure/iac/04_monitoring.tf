resource "azurerm_monitor_diagnostic_setting" "webapp" {
  name                       = "${local.project}-app-diag"
  target_resource_id         = module.webapp.id
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.law.id

  # Container stdout/stderr — this is what you see in Log Stream.
  enabled_log {
    category = "AppServiceConsoleLogs"
  }

  # HTTP request logs.
  enabled_log {
    category = "AppServiceHTTPLogs"
  }

  # Container pull/start logs — useful for diagnosing startup failures.
  enabled_log {
    category = "AppServicePlatformLogs"
  }
}
