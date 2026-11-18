data "aws_caller_identity" "current" {}

data "aws_organizations_organization" "current" {
  count = var.master_account_id == "" ? 0 : 1
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
  name                 = "${var.name_prefix}-lambda-execution"
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

  dynamic "statement" {
    for_each = var.master_account_id == "" ? [] : [data.aws_organizations_organization.current[0].id]

    content {
      sid       = "AssumeReadOnlyRoleInOrganization"
      effect    = "Allow"
      actions   = ["sts:AssumeRole", "sts:SetSourceIdentity"]
      resources = ["arn:aws:iam::*:role/${var.target_role_name}"]

      condition {
        test     = "StringEquals"
        variable = "aws:ResourceOrgID"
        values   = [statement.value]
      }
    }
  }

  dynamic "statement" {
    for_each = var.master_account_id == "" ? [] : [true]

    content {
      sid       = "DiscoverOrganizationAccounts"
      effect    = "Allow"
      actions   = ["organizations:ListAccounts"]
      resources = ["*"]
    }
  }

  statement {
    sid       = "ReadCallerIdentity"
    effect    = "Allow"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_execution" {
  name   = "${var.name_prefix}-lambda-execution"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_execution.json
}
