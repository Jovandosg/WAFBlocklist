module "api_gateway" {
  source = "./modules/api_gateway"

  name_prefix            = local.name_prefix
  cors_origins           = var.cors_origins
  log_retention_days     = var.log_retention_days
  lambda_timeout_seconds = var.lambda_timeout_seconds
  lambda_function_name   = module.lambda.function_name
  lambda_invoke_arn      = module.lambda.invoke_arn
}
