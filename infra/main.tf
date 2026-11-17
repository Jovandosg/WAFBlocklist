locals {
  name_prefix          = "${var.project_name}-${var.environment}"
  lambda_function_name = "${local.name_prefix}-api"
  log_group_name       = "/aws/lambda/${local.lambda_function_name}"
  target_role_arns     = [for account_id in var.target_account_ids : "arn:aws:iam::${account_id}:role/${var.target_role_name}"]
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = local.log_group_name
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    sid     = "LambdaServiceAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_execution" {
  name                 = "${local.name_prefix}-lambda-execution"
  assume_role_policy   = data.aws_iam_policy_document.lambda_assume_role.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "lambda_execution" {
  statement {
    sid    = "WriteLambdaLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid       = "AssumeOnlyConfiguredTargetRoles"
    effect    = "Allow"
    actions   = ["sts:AssumeRole"]
    resources = local.target_role_arns
  }

  statement {
    sid       = "ReadCallerIdentity"
    effect    = "Allow"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_execution" {
  name   = "${local.name_prefix}-lambda-execution"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_execution.json
}

resource "terraform_data" "lambda_package" {
  triggers_replace = [
    filesha256("${path.root}/../backend/requirements.txt"),
    filesha256("${path.root}/../backend/handler.py"),
    filesha256("${path.root}/../backend/app/main.py"),
    filesha256("${path.root}/../backend/app/api/routes.py"),
    filesha256("${path.root}/../backend/app/core/config.py"),
    filesha256("${path.root}/../backend/app/models/schemas.py"),
    filesha256("${path.root}/../backend/app/services/plans.py"),
    filesha256("${path.root}/../backend/app/integrations/aws/mock_adapter.py")
  ]

  provisioner "local-exec" {
    working_dir = path.root
    command     = "bash build-lambda.sh"
  }
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
      ENVIRONMENT     = var.environment
      API_PREFIX      = "/api/v1"
      CORS_ORIGINS    = var.cors_origins
      AWS_ACCOUNT_IDS = join(",", var.target_account_ids)
      AWS_ROLE_NAME   = var.target_role_name
      USE_MOCK_AWS    = length(var.target_account_ids) == 0 ? "true" : "false"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda_execution,
    terraform_data.lambda_package
  ]
}

resource "aws_apigatewayv2_api" "http" {
  name          = "${local.name_prefix}-http-api"
  protocol_type = "HTTP"
  description   = "WAFBlocklist FastAPI HTTP API"

  cors_configuration {
    allow_headers = ["content-type", "authorization"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_origins = [for origin in split(",", var.cors_origins) : trimspace(origin)]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
  timeout_milliseconds   = min(var.lambda_timeout_seconds * 1000, 30000)
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId               = "$context.requestId"
      extendedRequestId       = "$context.extendedRequestId"
      httpMethod              = "$context.httpMethod"
      routeKey                = "$context.routeKey"
      status                  = "$context.status"
      responseLatency         = "$context.responseLatency"
      integrationStatus       = "$context.integrationStatus"
      integrationErrorMessage = "$context.integrationErrorMessage"
      sourceIp                = "$context.identity.sourceIp"
    })
  }

  default_route_settings {
    detailed_metrics_enabled = true
    throttling_burst_limit   = 100
    throttling_rate_limit    = 50
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${local.name_prefix}"
  retention_in_days = var.log_retention_days
}
