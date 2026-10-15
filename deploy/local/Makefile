.PHONY: init up down logs ps backup restore new
init: ; test -f .env || (cp .env.example .env && sed -i "s/change-me/$$(openssl rand -hex 16)/" .env && echo ".env 생성됨")
up: init ; docker compose up -d --build
down: ; docker compose down
logs: ; docker compose logs -f --tail=100
ps: ; docker compose ps
# 새 서비스: make new SLUG=camping TOPIC="캠핑장 후기" ENTITY="site=name*,region"
new: ; cd ../../app && forge new $(SLUG) --topic "$(TOPIC)" --entity "$(ENTITY)"
backup: ; mkdir -p backups && docker compose exec -T db pg_dump -U forge forge | gzip > backups/forge-$$(date +%F-%H%M).sql.gz
restore: ; test -n "$(FILE)" && gunzip -c $(FILE) | docker compose exec -T db psql -U forge forge
