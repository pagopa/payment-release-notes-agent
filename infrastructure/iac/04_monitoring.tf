# ─────────────────────────────────────────────────────────────────────────────
# Diagnostic settings — route the webapp container logs to Log Analytics.
#
# Only the categories NOT already collected by the platform/policy diagnostic
# setting are enabled here (console/HTTP/platform). Audit, antivirus and metrics
# are intentionally left out: Azure rejects sending the same category to the
# same workspace from two different diagnostic settings.
# ─────────────────────────────────────────────────────────────────────────────

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
