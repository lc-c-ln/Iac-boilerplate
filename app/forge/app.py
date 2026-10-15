"""멀티테넌트 런타임: 한 프로세스가 specs/ 의 모든 서비스를 제공한다."""
import os
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from .db import DB
from .spec import Registry, ServiceSpec, validate_record

TEMPLATE = (Path(__file__).parent / "templates" / "service.html").read_text(encoding="utf-8")


class Signup(BaseModel): handle: str
class ThreadIn(BaseModel):
    body: str
    kind: str = "post"          # post | comment | review
    record_id: int | None = None
    parent_id: int | None = None
    rating: int | None = None
class ReactIn(BaseModel): target_id: int; kind: str = "like"


def create_app(specs_dir: str | Path = "specs", db_path: str = ":memory:") -> FastAPI:
    reg, db = Registry(Path(specs_dir)), DB(db_path)
    app = FastAPI(title="platform-forge")

    def tenant(slug: str) -> ServiceSpec:
        s = reg.get(slug)
        if not s: raise HTTPException(404, "서비스 없음")
        return s

    def me(slug: str, authorization: str | None = Header(None)):
        if not authorization: raise HTTPException(401, "Authorization: Bearer <token> 필요")
        u = db.user(slug, authorization.removeprefix("Bearer ").strip())
        if not u: raise HTTPException(401, "잘못된 토큰")
        return u

    @app.middleware("http")
    async def host_routing(request: Request, call_next):  # 커스텀 도메인 → /s/{slug}
        s = reg.by_host(request.headers.get("host", ""))
        if s and not request.url.path.startswith("/s/"):
            request.scope["path"] = f"/s/{s.slug}{request.url.path.rstrip('/') or '/'}"
        return await call_next(request)

    @app.get("/healthz")
    def healthz():
        db.one("SELECT 1 AS ok"); return {"ok": True}

    @app.get("/")
    def index():
        return [{"slug": s.slug, "name": s.name, "topic": s.topic, "url": f"/s/{s.slug}/"} for s in reg.all().values()]

    @app.get("/s/{slug}/", response_class=HTMLResponse)
    def page(slug: str):
        s = tenant(slug)
        return TEMPLATE.replace("__NAME__", s.name).replace("__TAGLINE__", s.tagline) \
                       .replace("__COLOR__", s.theme.get("color", "#2563eb")).replace("__SLUG__", s.slug)

    @app.get("/s/{slug}/api/spec")
    def spec(slug: str): return tenant(slug)

    @app.post("/s/{slug}/api/signup")
    def signup(slug: str, body: Signup):
        tenant(slug)
        try: return {"token": db.signup(slug, body.handle[:40])}
        except Exception: raise HTTPException(409, "이미 있는 handle")

    @app.get("/s/{slug}/api/e/{entity}")
    def list_(slug: str, entity: str, q: str | None = None, limit: int = 50, offset: int = 0):
        s = tenant(slug)
        if not s.entity(entity): raise HTTPException(404, "알 수 없는 객체")
        rows = db.list_records(slug, entity, q, min(limit, 100), offset)
        for r in rows: r["rating"] = db.rating(slug, r["id"])
        return rows

    @app.post("/s/{slug}/api/e/{entity}", status_code=201)
    def create(slug: str, entity: str, data: dict, user=Depends(me)):
        s = tenant(slug); ent = s.entity(entity)
        if not ent: raise HTTPException(404, "알 수 없는 객체")
        try: clean = validate_record(ent, data)
        except ValueError as e: raise HTTPException(422, str(e))
        status = "pending" if s.community.moderation == "approval" and user["role"] != "admin" else "published"
        return {"id": db.add_record(slug, entity, clean, user["id"], status), "status": status}

    @app.get("/s/{slug}/api/admin/pending")
    def pending(slug: str, user=Depends(me)):
        if user["role"] != "admin": raise HTTPException(403)
        return [r for e in tenant(slug).entities for r in db.list_records(slug, e.key, status="pending")]

    @app.post("/s/{slug}/api/records/{rid}/{action}")
    def moderate(slug: str, rid: int, action: str, user=Depends(me)):
        if user["role"] != "admin": raise HTTPException(403, "관리자만")
        status = {"approve": "published", "reject": "rejected"}.get(action)
        if not status or not db.set_status(slug, rid, status): raise HTTPException(404)
        return {"id": rid, "status": status}

    @app.get("/s/{slug}/api/threads")
    def threads(slug: str, record_id: int | None = None):
        tenant(slug); return db.list_threads(slug, record_id)

    @app.post("/s/{slug}/api/threads", status_code=201)
    def post_thread(slug: str, t: ThreadIn, user=Depends(me)):
        c = tenant(slug).community
        if t.kind not in ("post", "comment", "review"): raise HTTPException(422, "kind 오류")
        if t.kind == "review":
            if not c.reviews or t.record_id is None or not t.rating or not 1 <= t.rating <= 5:
                raise HTTPException(422, "리뷰: record_id와 1~5 rating 필요 / 리뷰 비활성")
        elif not c.threads: raise HTTPException(403, "스레드 비활성")
        return {"id": db.add_thread(slug, t.record_id, t.parent_id, t.kind, user["id"], t.body[:5000], t.rating)}

    @app.post("/s/{slug}/api/react")
    def react(slug: str, r: ReactIn, user=Depends(me)):
        if r.kind not in tenant(slug).community.reactions: raise HTTPException(422, "허용되지 않은 반응")
        return {"count": db.react(slug, r.target_id, user["id"], r.kind)}

    return app


app = create_app(os.environ.get("SPECS_DIR", "specs"), os.environ.get("DATABASE_URL", "forge.db"))
