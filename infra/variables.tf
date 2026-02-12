variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-1"
}

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
  default     = "discord-recorder"
}

variable "vpc_id" {
  description = "VPC ID for Lambda and Fargate networking"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs (recommended)"
  type        = list(string)
  validation {
    condition     = length(var.private_subnet_ids) > 0
    error_message = "private_subnet_ids must not be empty."
  }
}

variable "public_subnet_ids" {
  description = "Public subnet IDs used when assignPublicIp is enabled"
  type        = list(string)
  default     = []
}

variable "assign_public_ip" {
  description = "Set true to avoid NAT cost by giving Fargate public egress"
  type        = bool
  default     = true
  validation {
    condition     = var.assign_public_ip ? length(var.public_subnet_ids) > 0 : true
    error_message = "public_subnet_ids must be set when assign_public_ip is true."
  }
}

variable "recorder_image_uri" {
  description = "ECR image URI for recorder worker"
  type        = string
}

variable "discord_bot_token_ssm_param_arn" {
  description = "ARN of SSM SecureString for DISCORD_BOT_TOKEN"
  type        = string
}

variable "openai_api_key_ssm_param_arn" {
  description = "ARN of SSM SecureString for OPENAI_API_KEY"
  type        = string
}

variable "target_voice_channel_id" {
  description = "Target Discord voice channel ID"
  type        = string
}

variable "minutes_text_channel_id" {
  description = "Minutes post destination channel ID"
  type        = string
}

variable "min_participants" {
  description = "Minimum participants before start allowed"
  type        = number
  default     = 2
}

variable "audio_chunk_minutes" {
  description = "Audio chunk size in minutes"
  type        = number
  default     = 10
}

variable "retention_days" {
  description = "Retention days for logs and intermediate files"
  type        = number
  default     = 7
}

variable "discord_public_key" {
  description = "Discord app public key for interaction signature verification"
  type        = string
}

variable "fargate_cpu" {
  description = "Fargate task CPU units"
  type        = number
  default     = 512
}

variable "fargate_memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 1024
}

variable "use_fargate_spot" {
  description = "Use FARGATE_SPOT first for lower cost"
  type        = bool
  default     = true
}
