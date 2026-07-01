<!-- markdownlint-disable -->
<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
| ---- | ------- |
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >=1.9.8 |
| <a name="requirement_azurerm"></a> [azurerm](#requirement\_azurerm) | ~> 4.0 |

## Modules

| Name | Source | Version |
| ---- | ------ | ------- |
| <a name="module_apim_api_payment_release_notes_v1"></a> [apim\_api\_payment\_release\_notes\_v1](#module\_apim\_api\_payment\_release\_notes\_v1) | git::https://github.com/pagopa/terraform-azurerm-v4.git//api_management_api | 7787f9ec0d71db411ebab613d7731a4286210c30 |
| <a name="module_storage"></a> [storage](#module\_storage) | git::https://github.com/pagopa/terraform-azurerm-v4.git//IDH/storage_account | 7787f9ec0d71db411ebab613d7731a4286210c30 |
| <a name="module_webapp"></a> [webapp](#module\_webapp) | git::https://github.com/pagopa/terraform-azurerm-v4.git//IDH/app_service_webapp | 7787f9ec0d71db411ebab613d7731a4286210c30 |

## Resources

| Name | Type |
| ---- | ---- |
| [azurerm_api_management_api_version_set.payment_release_notes](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/api_management_api_version_set) | resource |
| [azurerm_api_management_product.payment_release_notes](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/api_management_product) | resource |
| [azurerm_api_management_subscription.payment_release_notes](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/api_management_subscription) | resource |
| [azurerm_key_vault_access_policy.permissions](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault_access_policy) | resource |
| [azurerm_key_vault_secret.apim_subscription_key](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault_secret) | resource |
| [azurerm_key_vault_secret.connection_string](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/key_vault_secret) | resource |
| [azurerm_resource_group.rg](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/resource_group) | resource |
| [azurerm_key_vault.kv](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/key_vault) | data source |
| [azurerm_key_vault_secret.atlassian_token](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/key_vault_secret) | data source |
| [azurerm_key_vault_secret.atlassian_url](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/key_vault_secret) | data source |
| [azurerm_key_vault_secret.atlassian_user](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/key_vault_secret) | data source |
| [azurerm_key_vault_secret.github_token](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/key_vault_secret) | data source |
| [azurerm_private_dns_zone.azurewebsite](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/data-sources/private_dns_zone) | data source |

## Inputs

| Name | Description | Type | Default | Required |
| ---- | ----------- | ---- | ------- | :------: |
| <a name="input_allowed_subnet_ids"></a> [allowed\_subnet\_ids](#input\_allowed\_subnet\_ids) | n/a | `list(string)` | n/a | yes |
| <a name="input_api_management_name"></a> [api\_management\_name](#input\_api\_management\_name) | Name of the existing APIM instance. Leave empty to skip APIM resources. | `string` | `""` | no |
| <a name="input_api_management_rg"></a> [api\_management\_rg](#input\_api\_management\_rg) | Resource group of the existing APIM instance. | `string` | `""` | no |
| <a name="input_api_path"></a> [api\_path](#input\_api\_path) | Base path exposed on APIM for this service. | `string` | `"payment-release-notes"` | no |
| <a name="input_apim_hostname"></a> [apim\_hostname](#input\_apim\_hostname) | Public gateway hostname of the APIM instance (used in the OpenAPI spec). | `string` | `""` | no |
| <a name="input_azure_website_dns_zone_name"></a> [azure\_website\_dns\_zone\_name](#input\_azure\_website\_dns\_zone\_name) | n/a | `string` | n/a | yes |
| <a name="input_copilot_model"></a> [copilot\_model](#input\_copilot\_model) | Model ID for the GitHub Copilot / Models API. | `string` | `"openai/gpt-4.1"` | no |
| <a name="input_department_name"></a> [department\_name](#input\_department\_name) | Department name printed in the release notes document. | `string` | n/a | yes |
| <a name="input_docker_image_tag"></a> [docker\_image\_tag](#input\_docker\_image\_tag) | Docker image tag to deploy. | `string` | `"latest"` | no |
| <a name="input_document_language"></a> [document\_language](#input\_document\_language) | Language for the generated document. | `string` | `"Italian"` | no |
| <a name="input_domain"></a> [domain](#input\_domain) | n/a | `string` | n/a | yes |
| <a name="input_env"></a> [env](#input\_env) | n/a | `string` | n/a | yes |
| <a name="input_environments"></a> [environments](#input\_environments) | Comma-separated list of environments included in release notes. | `string` | `"dev,uat,prod"` | no |
| <a name="input_idh_app_service_resource_tier"></a> [idh\_app\_service\_resource\_tier](#input\_idh\_app\_service\_resource\_tier) | The IDH resource tier of app services. | `string` | n/a | yes |
| <a name="input_idh_storage_account_resource_tier"></a> [idh\_storage\_account\_resource\_tier](#input\_idh\_storage\_account\_resource\_tier) | The IDH resource tier of storage account. | `string` | n/a | yes |
| <a name="input_internal_dns_zone_resource_group_name"></a> [internal\_dns\_zone\_resource\_group\_name](#input\_internal\_dns\_zone\_resource\_group\_name) | n/a | `string` | n/a | yes |
| <a name="input_kv_name"></a> [kv\_name](#input\_kv\_name) | Name of the existing Key Vault instance. | `string` | n/a | yes |
| <a name="input_kv_resource_group_name"></a> [kv\_resource\_group\_name](#input\_kv\_resource\_group\_name) | Resource group of the existing Key Vault instance. | `string` | n/a | yes |
| <a name="input_llm_provider"></a> [llm\_provider](#input\_llm\_provider) | LLM provider: copilot \| openai \| anthropic | `string` | `"copilot"` | no |
| <a name="input_location"></a> [location](#input\_location) | n/a | `string` | n/a | yes |
| <a name="input_location_short"></a> [location\_short](#input\_location\_short) | Location short for italy: itn | `string` | `"itn"` | no |
| <a name="input_log_level"></a> [log\_level](#input\_log\_level) | Python log level: DEBUG \| INFO \| WARNING \| ERROR | `string` | `"INFO"` | no |
| <a name="input_prefix"></a> [prefix](#input\_prefix) | n/a | `string` | n/a | yes |
| <a name="input_private_dns_zone_blob_ids"></a> [private\_dns\_zone\_blob\_ids](#input\_private\_dns\_zone\_blob\_ids) | n/a | `list(string)` | n/a | yes |
| <a name="input_stale_job_minutes"></a> [stale\_job\_minutes](#input\_stale\_job\_minutes) | Minutes after which a pending job is considered stale and marked as failed. | `number` | `20` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | n/a | `map(string)` | `{}` | no |
| <a name="input_vnet_name"></a> [vnet\_name](#input\_vnet\_name) | Name of the existing VNet where the webapp outbound subnet lives. | `string` | n/a | yes |
| <a name="input_vnet_rg"></a> [vnet\_rg](#input\_vnet\_rg) | Resource group of the existing VNet. | `string` | n/a | yes |

## Outputs

No outputs.
<!-- END_TF_DOCS -->
