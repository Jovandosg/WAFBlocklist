output "api_gateway_url" {
  description = "Public URL of the HTTP API."
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "api_gateway_id" {
  description = "HTTP API identifier."
  value       = aws_apigatewayv2_api.http.id
}

output "lambda_function_name" {
  description = "Deployed Lambda function name."
  value       = aws_lambda_function.api.function_name
}

output "lambda_execution_role_arn" {
  description = "Lambda execution role ARN."
  value       = aws_iam_role.lambda_execution.arn
}

output "cloudwatch_log_group_name" {
  description = "Lambda CloudWatch log group."
  value       = aws_cloudwatch_log_group.lambda.name
}
