variable "name_prefix" {
  description = "Prefix used for AWS resource names."
  type        = string
}

variable "cors_origins" {
  description = "Comma-separated browser origins allowed by the API."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout used to set the API integration timeout."
  type        = number
}

variable "lambda_function_name" {
  description = "Name of the Lambda function invoked by API Gateway."
  type        = string
}

variable "lambda_invoke_arn" {
  description = "Lambda invocation ARN used by the API integration."
  type        = string
}
