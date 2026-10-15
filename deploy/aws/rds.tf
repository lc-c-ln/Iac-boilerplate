resource "random_password" "db" {
  length  = 32
  special = false # DATABASE_URL에 그대로 넣기 위해 URL-unsafe 문자 제외
}

resource "aws_db_subnet_group" "main" {
  name       = var.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_instance" "main" {
  identifier                   = var.name
  engine                       = "postgres"
  engine_version               = "16"
  instance_class               = var.db_instance_class
  allocated_storage            = var.db_storage_gb
  max_allocated_storage        = var.db_storage_gb * 10
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_name                      = "forge"
  username                     = "forge"
  password                     = random_password.db.result
  db_subnet_group_name         = aws_db_subnet_group.main.name
  vpc_security_group_ids       = [aws_security_group.db.id]
  multi_az                     = var.db_multi_az
  backup_retention_period      = 7
  performance_insights_enabled = true
  auto_minor_version_upgrade   = true
  deletion_protection          = var.deletion_protection
  skip_final_snapshot          = !var.deletion_protection
  final_snapshot_identifier    = var.deletion_protection ? "${var.name}-final" : null
  apply_immediately            = false
}

# 앱은 이 시크릿 하나(DATABASE_URL)만 주입받는다.
resource "aws_secretsmanager_secret" "database_url" {
  name_prefix             = "${var.name}/database-url-"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = "postgresql://forge:${random_password.db.result}@${aws_db_instance.main.address}:5432/forge"
}
