terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.60" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # 팀 운영 시 원격 상태 권장:
  # backend "s3" { bucket = "..." key = "platform-forge/terraform.tfstate" region = "ap-northeast-2" dynamodb_table = "..." }
}

provider "aws" {
  region = var.region
  default_tags { tags = { Project = var.name, ManagedBy = "terraform" } }
}

data "aws_availability_zones" "available" { state = "available" }
