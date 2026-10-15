"""범용 스키마. 모든 테이블에 tenant(=slug) 컬럼 → 서비스가 늘어도 마이그레이션이 없다.
DATABASE_URL: sqlite 경로(':memory:' 포함) 또는 postgresql://... (로컬/AWS 공통)."""
import json, secrets, sqlite3, threading, time
from contextlib import contextmanager

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, tenant TEXT, handle TEXT,
  role TEXT DEFAULT 'member', provider TEXT DEFAULT 'token', provider_uid TEXT, email TEXT, created REAL,
  UNIQUE(tenant, handle), UNIQUE(tenant, provider, provider_uid));
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, tenant TEXT, user_id INTEGER, expires REAL);
CREATE TABLE IF NOT EXISTS auth_nonces(id TEXT PRIMARY KEY, tenant TEXT, kind TEXT, created REAL, used INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, tenant TEXT, entity TEXT, data TEXT,
  author_id INTEGER, status TEXT DEFAULT 'published', created REAL);
CREATE INDEX IF NOT EXISTS ix_rec ON records(tenant, entity, status, created);
CREATE TABLE IF NOT EXISTS threads(id INTEGER PRIMARY KEY, tenant TEXT, record_id INTEGER, parent_id INTEGER,
  kind TEXT, user_id INTEGER, body TEXT, rating INTEGER, created REAL);
CREATE INDEX IF NOT EXISTS ix_thr ON threads(tenant, record_id, created);
CREATE TABLE IF NOT EXISTS reactions(tenant TEXT, target_id INTEGER, user_id INTEGER, kind TEXT,
  PRIMARY KEY(tenant, target_id, user_id, kind));
"""
SCHEMA_PG = SCHEMA_SQLITE.replace("INTEGER PRIMARY KEY", "BIGSERIAL PRIMARY KEY").replace("REAL", "DOUBLE PRECISION")


class DB:
    def __init__(self, url=":memory:"):
        self.pg = url.startswith(("postgres://", "postgresql://"))
        self.lock = threading.RLock()
        if self.pg:
            import psycopg
            from psycopg.rows import dict_row
            self.conn = psycopg.connect(url, row_factory=dict_row, autocommit=True)
            for stmt in filter(str.strip, SCHEMA_PG.split(";")):
                self.conn.execute(stmt)
        else:
            self.conn = sqlite3.connect(url, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.executescript(SCHEMA_SQLITE)

    def q(self, sql, args=()):
        """SELECT. '?' 플레이스홀더를 두 드라이버에서 공통 사용."""
        with self.lock:
            return self.conn.execute(sql.replace("?", "%s") if self.pg else sql, args).fetchall()

    def one(self, sql, args=()):
        r = self.q(sql, args)
        return r[0] if r else None

    def write(self, sql, args=(), returning=False):
        """INSERT/UPDATE. returning=True면 새 id, 아니면 영향 행 수."""
        with self.lock:
            if self.pg:
                cur = self.conn.execute(sql.replace("?", "%s") + (" RETURNING id" if returning else ""), args)
                return cur.fetchone()["id"] if returning else cur.rowcount
            with self.conn:
                cur = self.conn.execute(sql, args)
            return cur.lastrowid if returning else cur.rowcount

    # ---- 계정 / 세션 ----
    def create_user(self, tenant, handle, provider="token", uid=None, email=None):
        """첫 가입자 = 관리자. handle이 겹치면 -2, -3 … 접미사. (user_id, created) 반환."""
        if uid is not None:
            u = self.one("SELECT id FROM users WHERE tenant=? AND provider=? AND provider_uid=?", (tenant, provider, uid))
            if u: return u["id"], False
        first = self.one("SELECT 1 AS x FROM users WHERE tenant=? LIMIT 1", (tenant,)) is None
        base, n, h = (handle or "user")[:40], 1, (handle or "user")[:40]
        while self.one("SELECT 1 AS x FROM users WHERE tenant=? AND handle=?", (tenant, h)):
            n += 1; h = f"{base}-{n}"
        uid_ = self.write("INSERT INTO users(tenant,handle,role,provider,provider_uid,email,created) VALUES(?,?,?,?,?,?,?)",
                          (tenant, h, "admin" if first else "member", provider, uid, email, time.time()), True)
        return uid_, True

    def create_session(self, tenant, user_id, ttl=30 * 86400):
        tok = secrets.token_urlsafe(32)
        self.write("INSERT INTO sessions VALUES(?,?,?,?)", (tok, tenant, user_id, time.time() + ttl))
        return tok

    def signup(self, tenant, handle):
        """provider=token (개발/내부용): handle만으로 가입. 중복이면 ValueError."""
        if self.one("SELECT 1 AS x FROM users WHERE tenant=? AND handle=?", (tenant, handle)):
            raise ValueError("이미 있는 handle")
        uid, _ = self.create_user(tenant, handle)
        return self.create_session(tenant, uid)

    def user(self, tenant, token):
        return self.one("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                        "WHERE s.tenant=? AND s.token=? AND s.expires>?", (tenant, token, time.time()))

    def revoke(self, tenant, token):
        self.write("DELETE FROM sessions WHERE tenant=? AND token=?", (tenant, token))

    # ---- 1회용 nonce (PortOne identityVerificationId 등 재사용 방지) ----
    def nonce_new(self, tenant, kind):
        nid = secrets.token_urlsafe(18)
        self.write("INSERT INTO auth_nonces(id,tenant,kind,created) VALUES(?,?,?,?)", (nid, tenant, kind, time.time()))
        return nid

    def nonce_use(self, tenant, kind, nid, ttl=900):
        """미사용 + ttl 이내일 때만 1회 소비. 성공 시 True."""
        return self.write("UPDATE auth_nonces SET used=1 WHERE id=? AND tenant=? AND kind=? AND used=0 AND created>?",
                          (nid, tenant, kind, time.time() - ttl)) == 1

    def add_record(self, tenant, entity, data, author, status):
        return self.write("INSERT INTO records(tenant,entity,data,author_id,status,created) VALUES(?,?,?,?,?,?)",
                          (tenant, entity, json.dumps(data, ensure_ascii=False), author, status, time.time()), True)

    def list_records(self, tenant, entity, q=None, limit=50, offset=0, status="published"):
        rows = self.q("SELECT * FROM records WHERE tenant=? AND entity=? AND status=? ORDER BY created DESC",
                      (tenant, entity, status))
        out = [self._rec(r) for r in rows]
        if q:
            out = [r for r in out if q.lower() in json.dumps(r["data"], ensure_ascii=False).lower()]
        return out[offset:offset + limit]

    def get_record(self, tenant, rid):
        r = self.one("SELECT * FROM records WHERE tenant=? AND id=?", (tenant, rid))
        return self._rec(r) if r else None

    def set_status(self, tenant, rid, status):
        return self.write("UPDATE records SET status=? WHERE tenant=? AND id=?", (status, tenant, rid))

    def add_thread(self, tenant, record_id, parent_id, kind, user_id, body, rating):
        return self.write("INSERT INTO threads(tenant,record_id,parent_id,kind,user_id,body,rating,created)"
                          " VALUES(?,?,?,?,?,?,?,?)",
                          (tenant, record_id, parent_id, kind, user_id, body, rating, time.time()), True)

    def list_threads(self, tenant, record_id=None):
        sql, args = "SELECT t.*, u.handle FROM threads t JOIN users u ON u.id=t.user_id WHERE t.tenant=?", [tenant]
        if record_id is not None: sql += " AND t.record_id=?"; args.append(record_id)
        return [dict(r) for r in self.q(sql + " ORDER BY t.created", args)]

    def rating(self, tenant, rid):
        r = self.one("SELECT AVG(rating) AS a, COUNT(rating) AS n FROM threads WHERE tenant=? AND record_id=? "
                     "AND kind='review'", (tenant, rid))
        return {"avg": round(float(r["a"]), 2) if r["a"] else None, "count": r["n"]}

    def react(self, tenant, target, user, kind):
        self.write("INSERT INTO reactions VALUES(?,?,?,?) ON CONFLICT DO NOTHING", (tenant, target, user, kind))
        return self.one("SELECT COUNT(*) AS n FROM reactions WHERE tenant=? AND target_id=? AND kind=?",
                        (tenant, target, kind))["n"]

    @staticmethod
    def _rec(r):
        d = dict(r)
        d["data"] = json.loads(d["data"]) if isinstance(d["data"], str) else d["data"]
        return d
