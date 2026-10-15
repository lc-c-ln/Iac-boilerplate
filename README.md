# platform-forge

**주제 + 객체만 정하면 커뮤니티/플랫폼이 생기는 멀티테넌트 뼈대**, 그리고 그것을 올리는 두 가지 인프라 세트.

```
platform-forge/
├─ app/                 애플리케이션 (FastAPI, 스펙 기반 멀티테넌트)
│  ├─ specs/*.yaml      서비스 1개 = 파일 1개
│  └─ forge/            스펙 스키마·API·범용 UI·CLI(forge)
├─ deploy/
│  ├─ local/            ① LOCAL / On-premise : Docker Compose (Caddy + app + Postgres)
│  └─ aws/              ② AWS : Terraform (ALB + ECS Fargate + RDS + ACM + ECR)
└─ .github/workflows/   CI (테스트 SQLite/Postgres, terraform validate, compose config)
```

두 세트는 **같은 이미지, 같은 Postgres, 같은 `DATABASE_URL` 규약**을 쓴다. 환경 차이는 deploy/ 아래에만 있다.

## 서비스 만들기
```bash
cd app && pip install -e . 
forge new camping --topic "캠핑장 후기" \
  --entity "site=name*,region,price:number" --entity "gear=name*,type:select(텐트|침낭)"
forge serve     # http://localhost:8000/s/camping/   (SQLite 기본, DATABASE_URL로 Postgres)
```
- 로컬/온프레: `deploy/local/README.md`
- AWS: `deploy/aws/README.md`

## 기본 제공 기능 (스펙으로 on/off)
가입(첫 가입자=관리자) · 객체 등록(필드 검증) · 검색 · 글/댓글 · 1~5점 리뷰 · 반응 · 승인제 모더레이션 · Host 기반 커스텀 도메인 · 스펙 핫 리로드

## 설계 결정
- 서비스별 코드/배포 대신 **단일 멀티테넌트 + 스펙**: 서비스 N개의 운영비가 N에 비례하지 않는다.
- 객체는 `tenant` 컬럼 + JSON으로 저장 → 필드 추가 = YAML 수정, 마이그레이션 없음. 대신 복잡한 쿼리/정렬은 약하다(JSONB 인덱스·전용 테이블로 승격 가능).
- 서비스 고유 요구는 코어의 스펙 옵션으로 추가해 모든 서비스가 공유. 서비스별 포크 금지.

## 로드맵
이메일/OAuth 인증 · 이미지 업로드(S3/MinIO) · SSR/SEO · 스팸·신고·레이트리밋 · 알림/피드 · 토픽→스펙 LLM 자동 생성 · 대형 테넌트 전용 DB 분리
