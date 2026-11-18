output "function_name" {
  description = "Deployed Lambda function name."
  value       = aws_lambda_function.api.function_name
}

output "invoke_arn" {
  description = "Lambda invocation ARN for API Gateway integration."
  value       = aws_lambda_function.api.invoke_arn
}

output "execution_role_arn" {
  description = "Lambda execution role ARN."
  value       = aws_iam_role.lambda_execution.arn
}

output "log_group_name" {
  description = "Lambda CloudWatch log group name."
  value       = aws_cloudwatch_log_group.lambda.name
}
