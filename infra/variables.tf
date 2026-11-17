variable "aws_region" {
  description = "AWS region for the API resources. CloudFront WAF queries still use us-east-1 in the application."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.environment))
    error_message = "environment must contain 2-16 lowercase letters, numbers or hyphens and start with a letter."
  }
}

variable "project_name" {
  description = "Short application name used in AWS resource names."
  type        = string
  default     = "wafblocklist"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.project_name))
    error_message = "project_name must contain lowercase letters, numbers or hyphens and start with a letter."
  }
}

variable "target_account_ids" {
  description = "AWS accounts where the Lambda may assume the read-only query role."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for account_id in var.target_account_ids : can(regex("^[0-9]{12}$", account_id))])
    error_message = "Every target account ID must be exactly 12 digits."
  }
}

variable "target_role_name" {
  description = "Role name deployed in each target account for read-only WAF/CloudFront queries."
  type        = string
  default     = "wafblocklist-readonly-query"
}

variable "cors_origins" {
  description = "Comma-separated browser origins allowed by the FastAPI CORS middleware."
  type        = string
  default     = "http://localhost:3000"
}

variable "lambda_timeout_seconds" {
  description = "Maximum Lambda execution time."
  type        = number
  default     = 60

  validation {
    condition     = var.lambda_timeout_seconds >= 3 && var.lambda_timeout_seconds <= 900
    error_message = "lambda_timeout_seconds must be between 3 and 900."
  }
}

variable "lambda_memory_size" {
  description = "Lambda memory size in MB."
  type        = number
  default     = 512

  validation {
    condition     = var.lambda_memory_size >= 128 && var.lambda_memory_size <= 10240
    error_message = "lambda_memory_size must be between 128 and 10240 MB."
  }
}

variable "lambda_reserved_concurrency" {
  description = "Maximum concurrent queries to protect target accounts. Set to null to omit the limit."
  type        = number
  default     = 10
  nullable    = true

  validation {
    condition     = var.lambda_reserved_concurrency == null || (var.lambda_reserved_concurrency >= 1 && var.lambda_reserved_concurrency <= 1000)
    error_message = "lambda_reserved_concurrency must be null or between 1 and 1000."
  }
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 30
}

variable "lambda_package_path" {
  description = "Path to the Lambda ZIP, relative to the infra directory, after running build-lambda.sh."
  type        = string
  default     = "../.build/wafblocklist-lambda.zip"
}

variable "tags" {
  description = "Additional tags for provisioned resources."
  type        = map(string)
  default     = {}
}
