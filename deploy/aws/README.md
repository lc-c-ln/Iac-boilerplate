# AWS

ALB → ECS Fargate(오토스케일) → RDS PostgreSQL 16. 시크릿은 Secrets Manager, 이미지는 ECR.

```
Internet ─▶ ALB (public) ─▶ ECS Fargate × N (private) ─▶ RDS Postgres (private)
                 │                    └─ DATABASE_URL ← Secrets Manager
                 └─ ACM 인증서(HTTPS)      └─ 로그 → CloudWatch
```

## 사용법
```bash
cd deploy/aws
cp terraform.tfvars.example terraform.tfvars   # domain 등 수정
terraform init && terraform apply
./scripts/deploy.sh                            # 이미지 빌드/푸시 + 롤링 배포
terraform output url
```
첫 `apply` 직후에는 ECR이 비어 있어 태스크가 뜨지 않는다 → `./scripts/deploy.sh`를 실행하면 정상화된다.

## 새 서비스 추가 (AWS)
`app/specs/<slug>.yaml` 추가 → PR → `./scripts/deploy.sh` (스펙은 이미지에 포함되므로 배포가 곧 서비스 생성).
인프라(VPC/DB/ALB)는 서비스 수와 무관하게 그대로다. 커스텀 도메인은 `extra_domains`에 추가하고 `terraform apply`.

## 비용 감각 (서울, 기본값 개략)
NAT 1개 + ALB + Fargate 2태스크 + db.t4g.small ≈ 월 $100~130. 줄이려면 `desired_count=1`, 개발 환경은 `deletion_protection=false`.
운영 전환 시 `db_multi_az=true`, `single_nat=false`.

## 주의
- 이 코드는 이 환경에서 `terraform fmt`로만 확인했고, provider 스키마 대상 `validate`/`plan`은 실행하지 못했다. 첫 적용 전에 `terraform plan`을 반드시 확인할 것(CI가 validate를 수행).
- 상태 파일 원격 백엔드(S3+DynamoDB)는 `versions.tf` 주석 참고.
