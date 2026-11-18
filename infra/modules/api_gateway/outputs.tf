output "api_endpoint" {
  description = "Public URL of the HTTP API."
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "api_id" {
  description = "HTTP API identifier."
  value       = aws_apigatewayv2_api.http.id
}
