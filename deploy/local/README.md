# Local / On-premise

Docker 한 대(노트북, 사내 서버, 미니PC)에서 전체 스택을 올린다.

```bash
cd deploy/local
make up                 # .env 자동 생성 → db + app + proxy 기동
open http://localhost/  # 서비스 목록
make new SLUG=camping TOPIC="캠핑장 후기" ENTITY="site=name*,region,price:number"
open http://localhost/s/camping/    # 재시작 없이 바로 열림
make backup             # backups/*.sql.gz
```

## 온프레미스 운영 메모
- **도메인/HTTPS**: `.env`의 `SITE_ADDRESS=forge.example.com` → Caddy가 Let's Encrypt 인증서를 자동 발급(80/443 개방 필요).
  서비스별 도메인은 스펙의 `domain`에 적고 `SITE_ADDRESS`에 쉼표로 추가.
- **사내망 전용**: `SITE_ADDRESS=:80` 유지, 내부 DNS로 접근.
- **백업**: `make backup`을 cron에 등록(`0 3 * * * cd /opt/platform-forge/deploy/local && make backup`). 볼륨 `pgdata`가 유일한 상태.
- **업데이트**: `git pull && make up` (이미지 재빌드, DB 스키마는 `IF NOT EXISTS`로 자동 적용).
- **다중 서버로 확장**: Postgres를 별도 서버로 빼고 `DATABASE_URL`만 교체, app을 N개로 늘려 Caddy `reverse_proxy app1:8000 app2:8000`.
