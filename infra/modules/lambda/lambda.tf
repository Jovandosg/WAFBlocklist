locals {
  lambda_function_name = "${var.name_prefix}-api"
  log_group_name       = "/aws/lambda/${local.lambda_function_name}"
}

resource "aws_lambda_function" "api" {
  function_name = local.lambda_function_name
  role          = aws_iam_role.lambda_execution.arn
  handler       = "backend.handler.handler"
  runtime       = "python3.12"

  filename         = var.lambda_package_path
  source_code_hash = filebase64sha256(var.lambda_package_path)

  timeout                        = var.lambda_timeout_seconds
  memory_size                    = var.lambda_memory_size
  reserved_concurrent_executions = var.lambda_reserved_concurrency

  environment {
    variables = {
      ENVIRONMENT           = var.environment
      API_PREFIX            = "/api/v1"
      CORS_ORIGINS          = var.cors_origins
      AWS_MASTER_ACCOUNT_ID = var.master_account_id
      AWS_ROLE_NAME         = var.target_role_name
      USE_MOCK_AWS          = var.master_account_id == "" ? "true" : "false"
    }
  }

  lifecycle {
    precondition {
      condition     = var.master_account_id == "" || var.master_account_id == data.aws_caller_identity.current.account_id
      error_message = "Deploy the API using credentials for the configured Organizations management account."
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda_execution
  ]
}
