moved {
  from = aws_cloudwatch_log_group.lambda
  to   = module.lambda.aws_cloudwatch_log_group.lambda
}

moved {
  from = aws_iam_role.lambda_execution
  to   = module.lambda.aws_iam_role.lambda_execution
}

moved {
  from = aws_iam_role_policy.lambda_execution
  to   = module.lambda.aws_iam_role_policy.lambda_execution
}

moved {
  from = aws_lambda_function.api
  to   = module.lambda.aws_lambda_function.api
}

moved {
  from = aws_apigatewayv2_api.http
  to   = module.api_gateway.aws_apigatewayv2_api.http
}

moved {
  from = aws_apigatewayv2_integration.lambda
  to   = module.api_gateway.aws_apigatewayv2_integration.lambda
}

moved {
  from = aws_apigatewayv2_route.default
  to   = module.api_gateway.aws_apigatewayv2_route.default
}

moved {
  from = aws_apigatewayv2_stage.default
  to   = module.api_gateway.aws_apigatewayv2_stage.default
}

moved {
  from = aws_lambda_permission.api_gateway
  to   = module.api_gateway.aws_lambda_permission.api_gateway
}

moved {
  from = aws_cloudwatch_log_group.api_gateway
  to   = module.api_gateway.aws_cloudwatch_log_group.api_gateway
}
