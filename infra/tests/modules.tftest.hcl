mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "588361999793"
    }
  }

  mock_data "aws_organizations_organization" {
    defaults = {
      id = "o-example"
    }
  }

  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
}

run "mock_lambda" {
  command = plan

  module {
    source = "./modules/lambda"
  }

  variables {
    name_prefix                 = "wafblocklist-dev"
    environment                 = "dev"
    master_account_id           = ""
    target_role_name            = "wafblocklist-readonly-query"
    cors_origins                = "http://localhost:3000"
    lambda_package_path         = "../backend/requirements.txt"
    lambda_timeout_seconds      = 60
    lambda_memory_size          = 512
    lambda_reserved_concurrency = 10
    log_retention_days          = 30
  }

  assert {
    condition     = aws_lambda_function.api.environment[0].variables.USE_MOCK_AWS == "true"
    error_message = "An empty management account ID must enable mock mode."
  }

  assert {
    condition     = length(data.aws_organizations_organization.current) == 0
    error_message = "Mock mode must not discover the AWS Organization."
  }

  assert {
    condition     = !contains(keys(aws_lambda_function.api.environment[0].variables), "AWS_REGION")
    error_message = "AWS_REGION is reserved and must be provided by the Lambda runtime."
  }
}

run "aws_lambda" {
  command = plan

  module {
    source = "./modules/lambda"
  }

  variables {
    name_prefix                 = "wafblocklist-dev"
    environment                 = "dev"
    master_account_id           = "588361999793"
    target_role_name            = "wafblocklist-readonly-query"
    cors_origins                = "http://localhost:3000"
    lambda_package_path         = "../backend/requirements.txt"
    lambda_timeout_seconds      = 60
    lambda_memory_size          = 512
    lambda_reserved_concurrency = 10
    log_retention_days          = 30
  }

  assert {
    condition     = aws_lambda_function.api.environment[0].variables.USE_MOCK_AWS == "false"
    error_message = "A management account ID must enable AWS read-only mode."
  }

  assert {
    condition     = length(data.aws_organizations_organization.current) == 1
    error_message = "AWS mode must discover the AWS Organization."
  }
}

run "reject_wrong_management_account" {
  command = plan

  module {
    source = "./modules/lambda"
  }

  variables {
    name_prefix                 = "wafblocklist-dev"
    environment                 = "dev"
    master_account_id           = "111111111111"
    target_role_name            = "wafblocklist-readonly-query"
    cors_origins                = "http://localhost:3000"
    lambda_package_path         = "../backend/requirements.txt"
    lambda_timeout_seconds      = 60
    lambda_memory_size          = 512
    lambda_reserved_concurrency = 10
    log_retention_days          = 30
  }

  expect_failures = [aws_lambda_function.api]
}

run "api_integration" {
  command = plan

  module {
    source = "./modules/api_gateway"
  }

  variables {
    name_prefix            = "wafblocklist-dev"
    cors_origins           = "https://example.com, http://localhost:3000"
    log_retention_days     = 30
    lambda_timeout_seconds = 60
    lambda_function_name   = "wafblocklist-dev-api"
    lambda_invoke_arn      = "arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/arn:aws:lambda:us-east-1:588361999793:function:wafblocklist-dev-api/invocations"
  }

  assert {
    condition     = aws_apigatewayv2_integration.lambda.timeout_milliseconds == 30000
    error_message = "The API integration timeout must remain capped at 30 seconds."
  }

  assert {
    condition     = toset(aws_apigatewayv2_api.http.cors_configuration[0].allow_origins) == toset(["https://example.com", "http://localhost:3000"])
    error_message = "API CORS origins must be split and trimmed."
  }

  assert {
    condition     = aws_lambda_permission.api_gateway.function_name == "wafblocklist-dev-api"
    error_message = "API Gateway must invoke the configured Lambda function."
  }
}

run "root_composition" {
  command = plan

  variables {
    environment         = "dev"
    master_account_id   = "588361999793"
    lambda_package_path = "../backend/requirements.txt"
  }

  assert {
    condition     = output.lambda_function_name == "wafblocklist-dev-api"
    error_message = "The root configuration must expose the Lambda function name."
  }

  assert {
    condition     = output.cloudwatch_log_group_name == "/aws/lambda/wafblocklist-dev-api"
    error_message = "The root configuration must expose the Lambda log group name."
  }
}
