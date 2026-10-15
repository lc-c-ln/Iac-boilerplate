import os
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from forge.app import create_app

SPEC = """
slug: {slug}
name: T
topic: t
auth: {auth}
entities: [{{key: item, label: i, fields: [{{name: n, required: true}}]}}]
"""
calls = []


def mock_http(portone_status="VERIFIED", birth="1990-01-01", ci="CI-AAA"):
    def handler(req: httpx.Request):
        calls.append(req)
        u = str(req.url)
        if u.startswith("https://kauth.kakao.com/oauth/token"):
            return httpx.Response(200, json={"access_token": "KAT"})
        if u.startswith("https://kapi.kakao.com/v2/user/me"):
            assert req.headers["authorization"] == "Bearer KAT"
            return httpx.Response(200, json={"id": 777, "kakao_account": {"profile": {"nickname": "홍 길동!"}}})
        if "api.portone.io/identity-verifications/" in u:
            assert req.headers["authorization"] == "PortOne PSECRET"
            return httpx.Response(200, json={"status": portone_status,
                                             "verifiedCustomer": {"ci": ci, "birthDate": birth, "name": "홍길동"}})
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)
    monkeypatch.setenv("KAKAO_REST_API_KEY", "RESTKEY")
    monkeypatch.setenv("PORTONE_API_SECRET", "PSECRET")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://forge.test")


def client(tmp_path, slug, auth, http=None):
    if os.environ.get("TEST_DATABASE_URL"):
        import psycopg
        with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as cn:
            cn.execute("DROP TABLE IF EXISTS users, sessions, auth_nonces, records, threads, reactions")
    (tmp_path / f"{slug}.yaml").write_text(SPEC.format(slug=slug, auth=auth), encoding="utf-8")
    return TestClient(create_app(tmp_path, os.environ.get("TEST_DATABASE_URL", ":memory:"), http or mock_http()), base_url="https://testserver", follow_redirects=False)


def test_kakao_flow(tmp_path):
    c = client(tmp_path, "kk", "{provider: kakao}")
    assert c.post("/s/kk/api/signup", json={"handle": "x"}).status_code == 404   # 핸들 가입 차단
    r = c.get("/s/kk/auth/kakao/login")
    loc = urlparse(r.headers["location"]); q = parse_qs(loc.query)
    assert loc.netloc == "kauth.kakao.com" and q["client_id"] == ["RESTKEY"]
    assert q["redirect_uri"] == ["https://forge.test/s/kk/auth/kakao/callback"]
    # state 변조 / 쿠키 없는 브라우저 → 거부
    assert "bad_state" in c.get("/s/kk/auth/kakao/callback", params={"code": "c", "state": "a.1.b"}).headers["location"]
    other = TestClient(c.app, base_url="https://testserver", follow_redirects=False)
    assert "bad_state" in other.get("/s/kk/auth/kakao/callback", params={"code": "c", "state": q["state"][0]}).headers["location"]
    # 정상
    r = c.get("/s/kk/auth/kakao/callback", params={"code": "c", "state": q["state"][0]})
    token = r.headers["location"].split("#token=")[1]
    h = {"Authorization": "Bearer " + token}
    assert c.post("/s/kk/api/e/item", json={"n": "a"}, headers=h).status_code == 201
    # 같은 카카오 계정으로 다시 로그인하면 같은 사용자
    c.get("/s/kk/auth/kakao/login")
    st = parse_qs(urlparse(c.get("/s/kk/auth/kakao/login").headers["location"]).query)["state"][0]
    t2 = c.get("/s/kk/auth/kakao/callback", params={"code": "c", "state": st}).headers["location"].split("#token=")[1]
    assert t2 != token
    assert c.app.state.db.one("SELECT COUNT(*) AS n FROM users")["n"] == 1
    # 로그아웃
    c.post("/s/kk/api/auth/logout", headers=h)
    assert c.post("/s/kk/api/e/item", json={"n": "a"}, headers=h).status_code == 401


def test_kakao_denied(tmp_path):
    c = client(tmp_path, "kk", "{provider: kakao}")
    assert "kakao_denied" in c.get("/s/kk/auth/kakao/callback", params={"error": "access_denied"}).headers["location"]


PORTONE = "{provider: portone, portone: {store_id: store-1, channel_key: channel-key-1, min_age: 19}}"


def test_portone_flow_and_replay(tmp_path):
    c = client(tmp_path, "pp", PORTONE)
    cfg = c.get("/s/pp/api/auth/config").json()
    assert cfg["portone"] == {"storeId": "store-1", "channelKey": "channel-key-1"}
    vid = c.post("/s/pp/api/auth/portone/start").json()["identityVerificationId"]
    r = c.post("/s/pp/api/auth/portone/complete", json={"identityVerificationId": vid, "handle": "길동이"})
    assert r.status_code == 200 and r.json()["created"] is True
    # 같은 ID 재사용 / 서버가 발급하지 않은 ID → 거부
    assert c.post("/s/pp/api/auth/portone/complete", json={"identityVerificationId": vid}).status_code == 400
    assert c.post("/s/pp/api/auth/portone/complete", json={"identityVerificationId": "idv-forged"}).status_code == 400
    # 같은 사람(CI)이 다시 인증하면 새 계정이 아니라 기존 계정
    vid2 = c.post("/s/pp/api/auth/portone/start").json()["identityVerificationId"]
    r2 = c.post("/s/pp/api/auth/portone/complete", json={"identityVerificationId": vid2, "handle": "다른이름"}).json()
    assert r2["created"] is False
    # 원본 CI/이름은 DB 어디에도 저장되지 않는다 (HMAC 해시만)
    dump = " ".join(str(dict(row)) for row in c.app.state.db.q("SELECT * FROM users"))
    assert "CI-AAA" not in dump and "홍길동" not in dump and "portone" in dump


def test_portone_rejections(tmp_path):
    for kw, code in [({"portone_status": "FAILED"}, 401), ({"birth": "2015-05-05"}, 403)]:
        c = client(tmp_path, "pp", PORTONE, mock_http(**kw))
        vid = c.post("/s/pp/api/auth/portone/start").json()["identityVerificationId"]
        assert c.post("/s/pp/api/auth/portone/complete", json={"identityVerificationId": vid}).status_code == code
    c = client(tmp_path, "pp", PORTONE)
    vid = c.post("/s/pp/api/auth/portone/start").json()["identityVerificationId"]
    assert c.post("/s/pp/api/auth/portone/complete", json={"identityVerificationId": vid, "handle": "<script>"}).status_code == 422


def test_portone_requires_ids(tmp_path):
    (tmp_path / "bad.yaml").write_text(SPEC.format(slug="bad", auth="{provider: portone}"))
    c = TestClient(create_app(tmp_path, ":memory:", mock_http()))
    assert c.get("/").json() == []   # 검증 실패한 스펙은 로드되지 않음
