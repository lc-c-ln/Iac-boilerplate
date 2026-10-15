resource "aws_ecr_repository" "app" {
  name                 = var.name
  image_tag_mutability = "MUTABLE"
  force_delete         = !var.deletion_protection
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({ rules = [{
    rulePriority = 1, description = "최근 20개만 유지"
    selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 20 }
    action       = { type = "expire" }
  }] })
}
