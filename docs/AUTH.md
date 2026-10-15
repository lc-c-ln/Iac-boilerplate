# 인증 (회원가입/로그인)

서비스마다 `specs/<slug>.yaml`의 `auth.provider`로 가입 방식을 고른다. 한 배포에서 서비스별로 다르게 쓸 수 있다.

| provider | 용도 | 가입 흐름 |
|---|---|---|
| `token` (기본) | 개발·내부 테스트 | 핸들만 입력 → 세션 발급 |
| `kakao` | 소셜 로그인 | 카카오 OAuth2 → 닉네임으로 계정 생성 |
| `portone` | 본인인증 가입 | PortOne V2 본인인증 → CI 해시로 1인 1계정 |

공통: 로그인에 성공하면 서버 세션 토큰(30일, DB 저장, 로그아웃 시 폐기)을 발급하고 `Authorization: Bearer`로 사용한다.
첫 가입자는 해당 서비스의 관리자가 된다.

## 환경변수 (비밀값은 스펙/Git에 넣지 않는다)
| 이름 | 필요 | 설명 |
|---|---|---|
| `SESSION_SECRET` | kakao·portone | 16자 이상 랜덤. state 서명·CI 해시 키. **바꾸면 기존 portone 사용자 식별이 깨지므로 고정 보관** |
| `PUBLIC_BASE_URL` | kakao | 외부 접속 주소. 스펙에 `domain`이 있으면 그 도메인 우선 |
| `KAKAO_REST_API_KEY` / `KAKAO_CLIENT_SECRET` | kakao | 카카오 REST API 키 / (활성화한 경우) Client Secret |
| `PORTONE_API_SECRET` | portone | 포트원 V2 API Secret |

로컬은 `deploy/local/.env`, AWS는 `TF_VAR_kakao_rest_api_key` 등으로 주입(Secrets Manager에 저장되어 ECS가 읽음).

## 카카오 설정
1. [Kakao Developers](https://developers.kakao.com) → 앱 생성 → **카카오 로그인 활성화**
2. **Redirect URI** 등록: `https://<도메인>/s/<slug>/auth/kakao/callback` (서비스마다 1개씩. 로컬 테스트는 `http://localhost/s/<slug>/auth/kakao/callback`)
3. 동의항목: 닉네임(기본). 이메일 등은 비즈 앱 전환 후 `scope: ["account_email"]`
4. REST API 키 → `KAKAO_REST_API_KEY`, (보안 탭에서 Client Secret 사용 시) → `KAKAO_CLIENT_SECRET`
5. 스펙에 `auth: {provider: kakao}`

흐름: `/auth/kakao/login`(state 서명 + 브라우저 쿠키 바인딩) → 카카오 → `/auth/kakao/callback`에서 state·쿠키 검증 → 토큰 교환 → 사용자 조회 → 세션 발급 후 `/s/<slug>/#token=…`으로 복귀(fragment라 서버 로그·Referer에 남지 않음).

## 포트원 본인인증 설정
1. [PortOne 콘솔](https://admin.portone.io)에서 본인인증 채널(통신사/KG이니시스 등) 연동 → **Store ID**, **채널 키**, **API Secret** 확인
2. 스펙:
   ```yaml
   auth:
     provider: portone
     portone: {store_id: store-..., channel_key: channel-key-..., min_age: 19}
   ```
3. `PORTONE_API_SECRET` 설정

흐름: 브라우저 `POST /auth/portone/start`(서버가 1회용 `identityVerificationId` 발급) → PortOne SDK 인증창 → `POST /auth/portone/complete` → 서버가 **포트원 API로 직접 조회**해 `VERIFIED`·연령을 검증 → 세션 발급.
- 클라이언트가 보낸 결과는 신뢰하지 않는다 (서버 조회 필수, 서버가 발급하지 않았거나 이미 쓴 ID는 거부).
- **이름·생년월일·CI 원문은 저장하지 않는다.** CI의 HMAC-SHA256 해시만 저장 → 같은 사람이 다시 인증하면 기존 계정으로 로그인(중복 가입 방지).
- 본인인증 수수료/정책은 포트원·인증사 계약에 따른다.

## 이 코드에서 직접 확인하지 못한 것
외부 API(카카오, 포트원)는 모의 서버로만 테스트했다. 실제 키로 다음 두 가지를 첫 배포 때 확인할 것:
- 포트원 조회 엔드포인트/헤더(`GET /identity-verifications/{id}`, `Authorization: PortOne <secret>`)와 응답 필드(`status`, `verifiedCustomer.ci/birthDate`) — 변경 시 `forge/auth.py`의 `portone_complete` 한 곳만 수정
- 카카오 Redirect URI가 콘솔 등록값과 **정확히** 일치하는지 (프록시 뒤에서 https/도메인이 달라지면 `PUBLIC_BASE_URL`로 고정)
