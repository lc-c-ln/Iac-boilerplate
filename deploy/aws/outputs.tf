output "alb_dns_name" { value = aws_lb.main.dns_name }
output "url" { value = local.use_https ? "https://${var.domain}" : "http://${aws_lb.main.dns_name}" }
output "ecr_repository_url" { value = aws_ecr_repository.app.repository_url }
output "ecs_cluster" { value = aws_ecs_cluster.main.name }
output "ecs_service" { value = aws_ecs_service.app.name }
output "acm_validation_records" {
  description = "extra_domains 등 수동 DNS 검증이 필요한 레코드"
  value = local.use_https ? [for o in aws_acm_certificate.main[0].domain_validation_options : {
    domain = o.domain_name, name = o.resource_record_name, type = o.resource_record_type, value = o.resource_record_value
  }] : []
}
