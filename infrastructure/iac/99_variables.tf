variable "prefix" {
  type = string
  validation {
    condition     = length(var.prefix) <= 6
    error_message = "Max length is 6 chars."
  }
}

variable "env" {
  type = string
}

variable "location" {
  type = string
}

variable "location_short" {
  type = string
  validation {
    condition = (
      length(var.location_short) == 3
    )
    error_message = "Length must be 3 chars."
  }
  description = "Location short for italy: itn"
  default     = "itn"
}

variable "domain" {
  type = string
  validation {
    condition     = length(var.domain) <= 12
    error_message = "Max length is 12 chars."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}

# ─────────────────────────────────────────────────────────────────────────────
# Release Notes Agent — WebApp
# ─────────────────────────────────────────────────────────────────────────────

variable "idh_app_service_resource_tier" {
  type        = string
  description = "The IDH resource tier of app services."
}

variable "idh_storage_account_resource_tier" {
  type        = string
  description = "The IDH resource tier of storage account."
}

variable "vnet_name" {
  type        = string
  description = "Name of the existing VNet where the webapp outbound subnet lives."
}

variable "vnet_rg" {
  type        = string
  description = "Resource group of the existing VNet."
}

variable "docker_image_tag" {
  type        = string
  description = "Docker image tag to deploy."
  default     = "latest"
}

variable "llm_provider" {
  type        = string
  description = "LLM provider: copilot | openai | anthropic"
  default     = "copilot"
}

variable "copilot_model" {
  type        = string
  description = "Model ID for the GitHub Copilot / Models API."
  default     = "openai/gpt-4.1"
}


variable "environments" {
  type        = string
  description = "Comma-separated list of environments included in release notes."
  default     = "dev,uat,prod"
}

variable "responsible_team" {
  type        = string
  description = "Team name printed in the release notes document."
}

variable "document_language" {
  type        = string
  description = "Language for the generated document."
  default     = "Italian"
}

variable "department_name" {
  type        = string
  description = "Department name printed in the release notes document."
}

variable "log_level" {
  type        = string
  description = "Python log level: DEBUG | INFO | WARNING | ERROR"
  default     = "INFO"
}

variable "stale_job_minutes" {
  type        = number
  description = "Minutes after which a pending job is considered stale and marked as failed."
  default     = 20
}


variable "azure_website_dns_zone_name" {
  type = string
}

variable "private_dns_zone_blob_ids" {
  type = list(string)
}

variable "internal_dns_zone_resource_group_name" {
  type = string
}

variable "allowed_subnet_ids" {
  type = list(string)
}

# ─────────────────────────────────────────────────────────────────────────────
# APIM
# ─────────────────────────────────────────────────────────────────────────────

variable "api_management_name" {
  type        = string
  description = "Name of the existing APIM instance. Leave empty to skip APIM resources."
  default     = ""
}

variable "api_management_rg" {
  type        = string
  description = "Resource group of the existing APIM instance."
  default     = ""
}

variable "apim_hostname" {
  type        = string
  description = "Public gateway hostname of the APIM instance (used in the OpenAPI spec)."
  default     = ""
}

variable "api_path" {
  type        = string
  description = "Base path exposed on APIM for this service."
  default     = "payment-release-notes"
}

# ─────────────────────────────────────────────────────────────────────────────
# KV
# ─────────────────────────────────────────────────────────────────────────────
variable "kv_resource_group_name" {
  type        = string
  description = "Resource group of the existing Key Vault instance."
}

variable "kv_name" {
  type        = string
  description = "Name of the existing Key Vault instance."
}
