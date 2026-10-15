#!/usr/bin/env bash
# 이미지 빌드 → ECR push → ECS 롤링 배포. 사용: ./scripts/deploy.sh [tag]
set -euo pipefail
cd "$(dirname "$0")/.."
TAG="${1:-$(git rev-parse --short HEAD 2>/dev/null || date +%s)}"
REPO=$(terraform output -raw ecr_repository_url)
REGION=${AWS_REGION:-$(terraform output -raw 2>/dev/null region || echo ap-northeast-2)}
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${REPO%%/*}"
docker build --platform linux/amd64 -t "$REPO:$TAG" -t "$REPO:latest" ../../app
docker push "$REPO:$TAG"; docker push "$REPO:latest"
aws ecs update-service --region "$REGION" --cluster "$(terraform output -raw ecs_cluster)" \
  --service "$(terraform output -raw ecs_service)" --force-new-deployment >/dev/null
echo "배포 시작: $REPO:$TAG  →  $(terraform output -raw url)"
