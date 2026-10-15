resource "aws_lb" "main" {
  name               = var.name
  load_balancer_type = "application"
  subnets            = aws_subnet.public[*].id
  security_groups    = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "app" {
  name_prefix = "app-"
  vpc_id      = aws_vpc.main.id
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  health_check {
    path    = "/healthz"
    matcher = "200"
  }
  deregistration_delay = 30
  lifecycle { create_before_destroy = true }
}

# HTTPS 사용 시: 80 → 443 리다이렉트, 443 → 앱. 아니면 80 → 앱.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = local.use_https ? "redirect" : "forward"
    target_group_arn = local.use_https ? null : aws_lb_target_group.app.arn
    dynamic "redirect" {
      for_each = local.use_https ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = local.use_https ? 1 : 0
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.main[0].certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
