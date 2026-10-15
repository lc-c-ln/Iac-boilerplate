resource "aws_acm_certificate" "main" {
  count                     = local.use_https ? 1 : 0
  domain_name               = var.domain
  subject_alternative_names = var.extra_domains
  validation_method         = "DNS"
  lifecycle { create_before_destroy = true }
}

# Route53 존이 있으면 대표 도메인 검증 레코드를 자동 생성. extra_domains의 검증 CNAME은
# `terraform output acm_validation_records`로 확인해 각 도메인에 직접 등록.
resource "aws_route53_record" "validation" {
  for_each = local.use_https && var.route53_zone_id != "" ? {
    for o in aws_acm_certificate.main[0].domain_validation_options : o.domain_name => o
    if o.domain_name == var.domain
  } : {}
  zone_id = var.route53_zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  records = [each.value.resource_record_value]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "main" {
  count           = local.use_https ? 1 : 0
  certificate_arn = aws_acm_certificate.main[0].arn
  # 존이 없으면 수동 검증 후 apply가 완료된다(validation 대기).
}

resource "aws_route53_record" "app" {
  count   = local.use_https && var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain
  type    = "A"
  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
