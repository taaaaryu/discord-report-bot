output "api_base_url" {
  value       = aws_apigatewayv2_stage.prod.invoke_url
  description = "Base URL for Discord interactions endpoint"
}

output "discord_interactions_url" {
  value       = "${aws_apigatewayv2_stage.prod.invoke_url}/discord/interactions"
  description = "Set this URL in Discord application interactions endpoint"
}

output "ecs_cluster_name" {
  value       = aws_ecs_cluster.this.name
  description = "ECS cluster name"
}

output "ecs_task_definition" {
  value       = aws_ecs_task_definition.recorder.family
  description = "Recorder task definition family"
}
