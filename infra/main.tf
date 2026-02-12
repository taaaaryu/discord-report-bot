locals {
  app_name     = var.name_prefix
  task_subnets = var.assign_public_ip ? var.public_subnet_ids : var.private_subnet_ids
}

data "aws_caller_identity" "current" {}

data "archive_file" "start_lambda" {
  type        = "zip"
  source_file = "${path.module}/lambda/start_handler.py"
  output_path = "${path.module}/build/start_handler.zip"
}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${local.app_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.app_name}-interactions"
  retention_in_days = 14
}

resource "aws_ecs_cluster" "this" {
  name = "${local.app_name}-cluster"
}

resource "aws_security_group" "fargate" {
  name        = "${local.app_name}-fargate-sg"
  description = "Fargate worker SG"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_dynamodb_table" "session_lock" {
  name         = "${local.app_name}-session-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

resource "aws_iam_role" "ecs_execution" {
  name = "${local.app_name}-ecs-exec-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_default" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_ssm" {
  name = "${local.app_name}-ecs-exec-ssm"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameters", "ssm:GetParameter", "kms:Decrypt"]
      Resource = [var.discord_bot_token_ssm_param_arn, var.openai_api_key_ssm_param_arn, "*"]
    }]
  })
}

resource "aws_iam_role" "ecs_task" {
  name = "${local.app_name}-ecs-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_ecs_task_definition" "recorder" {
  family                   = "${local.app_name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.fargate_cpu)
  memory                   = tostring(var.fargate_memory)
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "recorder"
      image     = var.recorder_image_uri
      essential = true
      environment = [
        { name = "MIN_PARTICIPANTS", value = tostring(var.min_participants) },
        { name = "AUDIO_CHUNK_MINUTES", value = tostring(var.audio_chunk_minutes) },
        { name = "RETENTION_DAYS", value = tostring(var.retention_days) },
        { name = "TARGET_VOICE_CHANNEL_ID", value = var.target_voice_channel_id },
        { name = "MINUTES_TEXT_CHANNEL_ID", value = var.minutes_text_channel_id },
        { name = "AUTO_START", value = "false" }
      ]
      secrets = [
        { name = "DISCORD_BOT_TOKEN", valueFrom = var.discord_bot_token_ssm_param_arn },
        { name = "OPENAI_API_KEY", valueFrom = var.openai_api_key_ssm_param_arn }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.ecs.name
          awslogs-region        = var.region
          awslogs-stream-prefix = "worker"
        }
      }
    }
  ])
}

resource "aws_iam_role" "lambda" {
  name = "${local.app_name}-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = "${local.app_name}-lambda-policy"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ecs:RunTask"]
        Resource = [aws_ecs_task_definition.recorder.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = [aws_iam_role.ecs_execution.arn, aws_iam_role.ecs_task.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:DeleteItem"]
        Resource = [aws_dynamodb_table.session_lock.arn]
      }
    ]
  })
}

resource "aws_lambda_function" "interactions" {
  function_name    = "${local.app_name}-interactions"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "start_handler.handler"
  filename         = data.archive_file.start_lambda.output_path
  source_code_hash = data.archive_file.start_lambda.output_base64sha256
  timeout          = 20

  environment {
    variables = {
      CLUSTER_ARN             = aws_ecs_cluster.this.arn
      TASK_DEFINITION_ARN     = aws_ecs_task_definition.recorder.arn
      SUBNET_IDS              = join(",", local.task_subnets)
      SECURITY_GROUP_ID       = aws_security_group.fargate.id
      ASSIGN_PUBLIC_IP        = var.assign_public_ip ? "ENABLED" : "DISABLED"
      LOCK_TABLE_NAME         = aws_dynamodb_table.session_lock.name
      DISCORD_PUBLIC_KEY      = var.discord_public_key
      USE_FARGATE_SPOT        = var.use_fargate_spot ? "true" : "false"
      TARGET_VOICE_CHANNEL_ID = var.target_voice_channel_id
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

resource "aws_apigatewayv2_api" "http" {
  name          = "${local.app_name}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.interactions.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "interactions" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "POST /discord/interactions"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "prod" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "prod"
  auto_deploy = true
}

resource "aws_lambda_permission" "allow_apigw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.interactions.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
