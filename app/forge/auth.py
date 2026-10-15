"""회원가입/로그인 provider: token(개발용) · kakao(소셜 로그인) · portone(본인인증).

서비스별로 스펙의 auth.provider 로 선택한다. 비밀값은 환경변수로만 받는다:
  SESSION_SECRET        state 서명 / PortOne CI 해시용 (kakao·portone 사용 시 필수, 32자 이상 권장)
  KAKAO_REST_API_KEY    카카오 REST API 키 (client_id)
  KAKAO_CLIENT_SECRET   카카오 Client Secret (콘솔에서 활성화한 경우)
  PORTONE_API_SECRET    PortOne V2 API Secret
  PUBLIC_BASE_URL       외부 접속 주소 (예: https://forge.example.com) — 카카오 redirect_uri 생성에 사용
"""
import hashlib, hmac, os, re, secrets, time
from datetime import date
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

KAKAO_AUTHORIZE = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN = "https://kauth.kakao.com/oauth/token"
KAKAO_ME = "https://kapi.kakao.com/v2/user/me"
PORTONE_API = "https://api.portone.io"
HANDLE_RE = re.compile(r"^[0-9A-Za-z가-힣_-]{2,20}$")


def _sign(secret: str, msg: str) -> str:
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


class CompleteIn(BaseModel):
    identityVerificationId: str
    handle: str = ""


def build_router(reg, db, http: httpx.Client) -> APIRouter:
    r = APIRouter()

    def secret() -> str:
        s = os.environ.get("SESSION_SECRET", "")
        if len(s) < 16: raise HTTPException(503, "SESSION_SECRET 환경변수(16자 이상)가 필요합니다")
        return s

    def spec_for(slug, provider):
        s = reg.get(slug)
        if not s: raise HTTPException(404, "서비스 없음")
        if s.auth.provider != provider: raise HTTPException(404, f"이 서비스는 {provider} 인증을 쓰지 않습니다")
        return s

    def base_url(request: Request, spec) -> str:
        if spec.domain: return f"https://{spec.domain}"
        return os.environ.get("PUBLIC_BASE_URL", str(request.base_url)).rstrip("/")

    # ---------- 공통 ----------
    @r.get("/s/{slug}/api/auth/config")
    def config(slug: str):
        s = reg.get(slug)
        if not s: raise HTTPException(404, "서비스 없음")
        out = {"provider": s.auth.provider}
        if s.auth.provider == "kakao": out["login_url"] = f"/s/{slug}/auth/kakao/login"
        if s.auth.provider == "portone":
            out["portone"] = {"storeId": s.auth.portone.store_id, "channelKey": s.auth.portone.channel_key}
        return out

    @r.post("/s/{slug}/api/auth/logout")
    def logout(slug: str, authorization: str | None = Header(None)):
        if authorization: db.revoke(slug, authorization.removeprefix("Bearer ").strip())
        return {"ok": True}

    # ---------- 카카오 (OAuth2 authorization code) ----------
    @r.get("/s/{slug}/auth/kakao/login")
    def kakao_login(slug: str, request: Request):
        s = spec_for(slug, "kakao"); key = os.environ.get("KAKAO_REST_API_KEY")
        if not key: raise HTTPException(503, "KAKAO_REST_API_KEY 필요")
        nonce, ts = secrets.token_urlsafe(16), int(time.time())
        state = f"{nonce}.{ts}.{_sign(secret(), f'{slug}.{nonce}.{ts}')}"
        q = {"client_id": key, "response_type": "code", "state": state,
             "redirect_uri": f"{base_url(request, s)}/s/{slug}/auth/kakao/callback"}
        if s.auth.kakao.scope: q["scope"] = ",".join(s.auth.kakao.scope)
        resp = RedirectResponse(f"{KAKAO_AUTHORIZE}?{urlencode(q)}", status_code=302)
        # state를 이 브라우저에 묶는다 (CSRF/로그인 고정 방지)
        resp.set_cookie(f"forge_oauth_{slug}", nonce, max_age=600, httponly=True, samesite="lax",
                        secure=base_url(request, s).startswith("https"))
        return resp

    @r.get("/s/{slug}/auth/kakao/callback")
    def kakao_callback(slug: str, request: Request, code: str = "", state: str = "", error: str = ""):
        s = spec_for(slug, "kakao")
        home = f"/s/{slug}/"
        fail = lambda why: RedirectResponse(f"{home}#error={why}", status_code=302)
        if error or not code: return fail("kakao_denied")
        try:
            nonce, ts, sig = state.split(".")
            ok = hmac.compare_digest(sig, _sign(secret(), f"{slug}.{nonce}.{ts}")) and time.time() - int(ts) < 600
        except ValueError:
            ok = False
        if not ok or request.cookies.get(f"forge_oauth_{slug}") != nonce: return fail("bad_state")
        data = {"grant_type": "authorization_code", "client_id": os.environ["KAKAO_REST_API_KEY"], "code": code,
                "redirect_uri": f"{base_url(request, s)}/s/{slug}/auth/kakao/callback"}
        if os.environ.get("KAKAO_CLIENT_SECRET"): data["client_secret"] = os.environ["KAKAO_CLIENT_SECRET"]
        try:
            t = http.post(KAKAO_TOKEN, data=data); t.raise_for_status()
            me = http.get(KAKAO_ME, headers={"Authorization": f"Bearer {t.json()['access_token']}"}); me.raise_for_status()
            me = me.json()
        except (httpx.HTTPError, KeyError, ValueError):
            return fail("kakao_failed")
        acct = me.get("kakao_account") or {}
        nick = ((acct.get("profile") or {}).get("nickname") or (me.get("properties") or {}).get("nickname") or "")
        nick = re.sub(r"[^0-9A-Za-z가-힣_-]", "", nick)[:20] or "kakao"
        uid, _ = db.create_user(slug, nick, "kakao", str(me["id"]), acct.get("email"))
        token = db.create_session(slug, uid)
        resp = RedirectResponse(f"{home}#token={token}", status_code=302)  # fragment는 서버 로그/Referer에 남지 않음
        resp.delete_cookie(f"forge_oauth_{slug}")
        return resp

    # ---------- 포트원 본인인증 (V2) ----------
    @r.post("/s/{slug}/api/auth/portone/start")
    def portone_start(slug: str):
        s = spec_for(slug, "portone")
        # 서버가 발급한 ID만 인정 → 클라이언트가 남의 인증 ID를 끼워 넣거나 재사용하는 것을 막는다
        return {"identityVerificationId": f"idv-{db.nonce_new(slug, 'portone')}",
                "storeId": s.auth.portone.store_id, "channelKey": s.auth.portone.channel_key}

    @r.post("/s/{slug}/api/auth/portone/complete")
    def portone_complete(slug: str, body: CompleteIn):
        s = spec_for(slug, "portone"); sec = secret()
        api_secret = os.environ.get("PORTONE_API_SECRET")
        if not api_secret: raise HTTPException(503, "PORTONE_API_SECRET 필요")
        if body.handle and not HANDLE_RE.match(body.handle): raise HTTPException(422, "handle: 2~20자 한글/영문/숫자/_-")
        vid = body.identityVerificationId
        if not vid.startswith("idv-") or not db.nonce_use(slug, "portone", vid[4:]):
            raise HTTPException(400, "유효하지 않거나 이미 사용된 인증 요청")
        try:
            resp = http.get(f"{PORTONE_API}/identity-verifications/{vid}", headers={"Authorization": f"PortOne {api_secret}"})
            resp.raise_for_status(); v = resp.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, "포트원 조회 실패")
        cust = v.get("verifiedCustomer") or {}
        if v.get("status") != "VERIFIED" or not (cust.get("ci") or cust.get("di")):
            raise HTTPException(401, "본인인증이 완료되지 않음")
        if s.auth.portone.min_age:
            try:
                b = date.fromisoformat(cust["birthDate"]); t = date.today()
                age = t.year - b.year - ((t.month, t.day) < (b.month, b.day))
            except (KeyError, ValueError):
                raise HTTPException(401, "생년월일 확인 불가")
            if age < s.auth.portone.min_age: raise HTTPException(403, f"만 {s.auth.portone.min_age}세 이상만 가입할 수 있습니다")
        # 원본 CI/이름/생년월일은 저장하지 않는다. HMAC 해시만 → 1인 1계정 보장 + 유출 시에도 CI 복원 불가
        uid_hash = _sign(sec, "portone-ci:" + (cust.get("ci") or cust.get("di")))
        uid, created = db.create_user(slug, body.handle or "user", "portone", uid_hash)
        return {"token": db.create_session(slug, uid), "created": created}

    return r
