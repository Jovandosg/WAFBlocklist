variable "name_prefix" {
  description = "Prefix used for AWS resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
}

variable "master_account_id" {
  description = "AWS Organizations management account ID, or an empty string for mock mode."
  type        = string
}

variable "target_role_name" {
  description = "Read-only role name in each target account."
  type        = string
}

variable "cors_origins" {
  description = "Comma-separated browser origins allowed by the API."
  type        = string
}

variable "lambda_package_path" {
  description = "Path to the Lambda ZIP relative to the root configuration."
  type        = string
}

variable "lambda_timeout_seconds" {
  description = "Maximum Lambda execution time."
  type        = number
}

variable "lambda_memory_size" {
  description = "Lambda memory size in MB."
  type        = number
}

variable "lambda_reserved_concurrency" {
  description = "Maximum concurrent executions, or null for no reserved limit."
  type        = number
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
}
