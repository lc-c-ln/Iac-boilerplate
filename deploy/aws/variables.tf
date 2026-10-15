variable "name" {
  type    = string
  default = "platform-forge"
}
variable "region" {
  type    = string
  default = "ap-northeast-2"
}
variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

# --- 도메인 / HTTPS (비워 두면 ALB 기본 DNS로 HTTP 운영) ---
variable "domain" {
  description = "대표 도메인 (예: forge.example.com). Route53 호스티드 존이 있으면 ACM 검증·레코드 자동 생성"
  type        = string
  default     = ""
}
variable "route53_zone_id" {
  type    = string
  default = ""
}
variable "extra_domains" {
  description = "서비스별 커스텀 도메인(ACM SAN). 해당 도메인의 DNS 검증/CNAME은 각 도메인 소유자가 설정"
  type        = list(string)
  default     = []
}

# --- 앱 ---
variable "image_tag" {
  type    = string
  default = "latest"
}
variable "app_cpu" {
  type    = number
  default = 512
}
variable "app_memory" {
  type    = number
  default = 1024
}
variable "desired_count" {
  type    = number
  default = 2
}
variable "max_count" {
  type    = number
  default = 10
}

# --- DB ---
variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}
variable "db_storage_gb" {
  type    = number
  default = 20
}
variable "db_multi_az" {
  type    = bool
  default = false
}
variable "deletion_protection" {
  type    = bool
  default = true
}

# --- 비용 ---
variable "single_nat" {
  description = "true: NAT 1개(저렴) / false: AZ별 NAT(고가용)"
  type        = bool
  default     = true
}
