# Variables
variable "aws_access_key_id" {
  sensitive = true
}
variable "aws_secret_access_key" {
  sensitive = true
}
variable "databricks_instance" {}
variable "databricks_token" {
  sensitive = true
}
variable "databricks_job_id" {}

# provider.tf
provider "aws" {
  region = "us-east-1"
}

# AWS Account Identity (current account)
data "aws_caller_identity" "current" {}

# S3 Bucket (existing)
data "aws_s3_bucket" "existing_bucket" {
  bucket = "af-rearc-quest"
}

# Existing Lambda functions
resource "aws_lambda_function" "dataset_to_s3_package" {
  filename      = "dataset_to_s3_package.zip"  # Zip with Python code that calls Databricks Jobs API
  function_name = "Dataset_to_S3_Lambda"
  handler       = "dataset_to_s3_package.lambda_handler"
  runtime       = "python3.14"
  role          = aws_iam_role.lambda_role.arn
  timeout       = 300

  environment {
    variables = {
      AWS_ACCESS_KEY_IDs     = var.aws_access_key_id
      AWS_SECRET_ACCESS_KEYs = var.aws_secret_access_key
    }
  }
}

resource "aws_lambda_function" "api_to_s3_package" {
  filename      = "api_to_s3_package.zip"  # Zip with Python code that calls Databricks Jobs API
  function_name = "API_to_S3_Lambda"
  handler       = "api_to_s3_package.lambda_handler"
  runtime       = "python3.14"
  role          = aws_iam_role.lambda_role.arn
  timeout       = 300

  environment {
    variables = {
      AWS_ACCESS_KEY_IDs     = var.aws_access_key_id
      AWS_SECRET_ACCESS_KEYs = var.aws_secret_access_key
    }
  }
}

# SQS Queue (new)
resource "aws_sqs_queue" "data_queue" {
  name = "DatasetProcessingQueue"
  visibility_timeout_seconds = 310
}

# Allow S3 to send messages to SQS
resource "aws_sqs_queue_policy" "allow_s3" {
  queue_url = aws_sqs_queue.data_queue.id
  policy    = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = { Service = "s3.amazonaws.com" },
        Action = "sqs:SendMessage",
        Resource = aws_sqs_queue.data_queue.arn,
        Condition = {
          ArnLike = {
            "aws:SourceArn" = data.aws_s3_bucket.existing_bucket.arn
          },
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

# S3 Notification → SQS (trigger on JSON uploads)
resource "aws_s3_bucket_notification" "s3_to_sqs" {
  bucket = data.aws_s3_bucket.existing_bucket.id

  queue {
    queue_arn     = aws_sqs_queue.data_queue.arn
    events        = ["s3:ObjectCreated:*"]
    filter_suffix = ".json"
  }

  depends_on = [aws_sqs_queue_policy.allow_s3]
}

# CloudWatch Event Rule for Scheduled Lambda Execution
# 03:00 UTC daily
resource "aws_cloudwatch_event_rule" "daily_dataset_api" {
  name                = "DailyDatasetAPI"
  description         = "Trigger Dataset_to_S3 and API_to_S3 at 03:00 UTC daily"
  schedule_expression = "cron(00 16 * * ? *)"
}

# CloudWatch Event Targets → Existing Lambdas
resource "aws_cloudwatch_event_target" "dataset_to_s3_target" {
  rule      = aws_cloudwatch_event_rule.daily_dataset_api.name
  target_id = "DatasetToS3Target"
  arn       = aws_lambda_function.dataset_to_s3_package.arn
  depends_on = [aws_lambda_function.dataset_to_s3_package]
}

resource "aws_cloudwatch_event_target" "api_to_s3_target" {
  rule      = aws_cloudwatch_event_rule.daily_dataset_api.name
  target_id = "APIToS3Target"
  arn       = aws_lambda_function.api_to_s3_package.arn
  depends_on = [aws_lambda_function.api_to_s3_package]
}

# Permissions for CloudWatch to invoke the existing Lambdas
resource "aws_lambda_permission" "allow_cloudwatch_dataset_to_s3_package" {
  statement_id  = "AllowExecutionFromCloudWatchDatasetToS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dataset_to_s3_package.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_dataset_api.arn
  depends_on = [aws_lambda_function.dataset_to_s3_package]
}

resource "aws_lambda_permission" "allow_cloudwatch_api_to_s3_package" {
  statement_id  = "AllowExecutionFromCloudWatchAPIToS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_to_s3_package.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_dataset_api.arn
  depends_on = [aws_lambda_function.api_to_s3_package]
}

# analytics_notebook Lambda (SQS triggered) - calls Databricks job
resource "aws_lambda_function" "analytics_notebook_package" {
  filename      = "analytics_notebook_package.zip"  # Zip with Python code that calls Databricks Jobs API
  function_name = "analytics_notebook_SQS_Consumer"
  handler       = "analytics_notebook_package.lambda_handler"
  runtime       = "python3.14"
  role          = aws_iam_role.lambda_role.arn
  timeout       = 300

  environment {
    variables = {
      DATABRICKS_INSTANCE = var.databricks_instance
      DATABRICKS_TOKEN    = var.databricks_token
      DATABRICKS_JOB_ID   = var.databricks_job_id
    }
  }
}

# Connect Part 3 Lambda to SQS
resource "aws_lambda_event_source_mapping" "analytics_notebook_sqs_trigger" {
  event_source_arn = aws_sqs_queue.data_queue.arn
  function_name    = aws_lambda_function.analytics_notebook_package.arn
  batch_size       = 1
}

# IAM Role for Lambda functions (if not already existing)
# Make sure it has permissions to SQS, CloudWatch Logs
resource "aws_iam_role" "lambda_role" {
  name = "lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "lambda_policy" {
  name = "lambda-policy"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "sqs:*",
          "logs:*"
        ],
        Effect = "Allow",
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_policy" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}
