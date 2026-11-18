module "lambda" {
  source = "./modules/lambda"

  name_prefix                 = local.name_prefix
  environment                 = var.environment
  master_account_id           = var.master_account_id
  target_role_name            = var.target_role_name
  cors_origins                = var.cors_origins
  lambda_package_path         = var.lambda_package_path
  lambda_timeout_seconds      = var.lambda_timeout_seconds
  lambda_memory_size          = var.lambda_memory_size
  lambda_reserved_concurrency = var.lambda_reserved_concurrency
  log_retention_days          = var.log_retention_days
}
