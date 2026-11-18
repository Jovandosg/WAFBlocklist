output "api_gateway_url" {
  description = "Public URL of the HTTP API."
  value       = module.api_gateway.api_endpoint
}

output "api_gateway_id" {
  description = "HTTP API identifier."
  value       = module.api_gateway.api_id
}

output "lambda_function_name" {
  description = "Deployed Lambda function name."
  value       = module.lambda.function_name
}

output "lambda_execution_role_arn" {
  description = "Lambda execution role ARN."
  value       = module.lambda.execution_role_arn
}

output "cloudwatch_log_group_name" {
  description = "Lambda CloudWatch log group."
  value       = module.lambda.log_group_name
}
