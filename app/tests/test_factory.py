import os
from fastapi.testclient import TestClient
from forge.app import create_app
from forge.cli import parse_entity


def make(tmp_path, moderation="open"):
    (tmp_path / "gym.yaml").write_text(f"""
slug: boulder
name: 볼더링
topic: 클라이밍 암장
entities:
  - key: gym
    label: 암장
    fields: [{{name: name, type: text, required: true}}, {{name: grade, type: select, options: [V0, V1]}}]
community: {{moderation: {moderation}}}
""", encoding="utf-8")
    url = os.environ.get("TEST_DATABASE_URL", ":memory:")  # 지정 시 Postgres로 동일 테스트 수행
    app = create_app(tmp_path, url)
    if url != ":memory:":
        import psycopg
        with psycopg.connect(url, autocommit=True) as c:
            c.execute("TRUNCATE users, sessions, auth_nonces, records, threads, reactions RESTART IDENTITY")
    return TestClient(app)


def auth(c, h):
    return {"Authorization": "Bearer " + c.post("/s/boulder/api/signup", json={"handle": h}).json()["token"]}


def test_flow(tmp_path):
    c = make(tmp_path); a = auth(c, "admin")
    r = c.post("/s/boulder/api/e/gym", json={"name": "더클라임", "grade": "V1"}, headers=a)
    assert r.status_code == 201
    assert c.post("/s/boulder/api/e/gym", json={"grade": "V9"}, headers=a).status_code == 422
    assert c.post("/s/boulder/api/e/gym", json={"name": "x"}).status_code == 401
    rid = r.json()["id"]
    assert c.post("/s/boulder/api/threads", json={"kind": "review", "record_id": rid, "rating": 4, "body": "굿"}, headers=a).status_code == 201
    row = c.get("/s/boulder/api/e/gym").json()[0]
    assert row["rating"] == {"avg": 4.0, "count": 1}
    assert c.get("/s/boulder/").status_code == 200


def test_hot_add_service_and_moderation(tmp_path):
    c = make(tmp_path, "approval"); admin = auth(c, "admin"); m = auth(c, "member")
    rid = c.post("/s/boulder/api/e/gym", json={"name": "A"}, headers=m).json()
    assert rid["status"] == "pending" and c.get("/s/boulder/api/e/gym").json() == []
    assert c.post(f"/s/boulder/api/records/{rid['id']}/approve", headers=m).status_code == 403
    c.post(f"/s/boulder/api/records/{rid['id']}/approve", headers=admin)
    assert len(c.get("/s/boulder/api/e/gym").json()) == 1
    (tmp_path / "wine.yaml").write_text("slug: wine\nname: W\ntopic: t\nentities: [{key: bottle, label: b, fields: [{name: n}]}]")
    assert {s["slug"] for s in c.get("/").json()} == {"boulder", "wine"}  # 재시작 없이 서비스 추가


def test_dsl():
    e = parse_entity("gym=name*:text,grade:select(V0|V1)")
    assert e["fields"][0]["required"] and e["fields"][1]["options"] == ["V0", "V1"]
