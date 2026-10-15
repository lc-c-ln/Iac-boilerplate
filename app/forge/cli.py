"""forge new / validate / list / serve"""
import argparse, re, sys
from pathlib import Path
import yaml
from .spec import load_spec

SPECS = Path("specs")


def parse_entity(expr: str) -> dict:
    """'gym=name*:text,city*,grade:select(V0|V1|V2)'  (* = 필수, 타입 생략 시 text)"""
    key, _, fields = expr.partition("=")
    out = []
    for f in fields.split(","):
        m = re.fullmatch(r"([a-z_][a-z0-9_]*)(\*?)(?::(\w+)(?:\(([^)]*)\))?)?", f.strip())
        if not m: sys.exit(f"필드 형식 오류: {f}")
        name, req, typ, opts = m.groups()
        d = {"name": name, "type": typ or "text"}
        if req: d["required"] = True
        if opts: d["options"] = opts.split("|")
        out.append(d)
    return {"key": key.strip(), "label": key.strip(), "fields": out}


def cmd_new(a):
    spec = {"slug": a.slug, "name": a.name or a.slug, "topic": a.topic, "tagline": a.tagline or a.topic,
            "entities": [parse_entity(e) for e in a.entity],
            "community": {"moderation": a.moderation, "reviews": True, "threads": True, "reactions": ["like"]}}
    if a.domain: spec["domain"] = a.domain
    if a.auth == "kakao": spec["auth"] = {"provider": "kakao"}
    if a.auth == "portone":
        spec["auth"] = {"provider": "portone", "portone": {"store_id": a.portone_store_id or "store-REPLACE-ME",
                        "channel_key": a.portone_channel_key or "channel-key-REPLACE-ME", "min_age": a.min_age}}
    SPECS.mkdir(exist_ok=True)
    p = SPECS / f"{a.slug}.yaml"
    if p.exists(): sys.exit(f"{p} 이미 존재")
    p.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    load_spec(p)  # 검증
    print(f"생성됨: {p}  → 서버가 켜져 있으면 즉시 /s/{a.slug}/ 로 제공됩니다")


def cmd_validate(a):
    bad = 0
    for p in sorted(SPECS.glob("*.yaml")):
        if p.name.startswith("_"): continue
        try: s = load_spec(p); print(f"OK   {p.name} ({len(s.entities)} entities)")
        except Exception as e: bad += 1; print(f"FAIL {p.name}: {e}")
    sys.exit(1 if bad else 0)


def cmd_list(a):
    for p in sorted(SPECS.glob("*.yaml")):
        if not p.name.startswith("_"): s = load_spec(p); print(f"{s.slug:20} {s.topic}")


def cmd_serve(a):
    import uvicorn
    uvicorn.run("forge.app:app", host=a.host, port=a.port, reload=False)


def main():
    ap = argparse.ArgumentParser(prog="forge"); sub = ap.add_subparsers(required=True)
    n = sub.add_parser("new", help="주제+객체로 새 서비스 생성"); n.set_defaults(fn=cmd_new)
    n.add_argument("slug"); n.add_argument("--topic", required=True); n.add_argument("--name"); n.add_argument("--tagline")
    n.add_argument("--entity", action="append", required=True, help="예: 'gym=name*,city*,grade:select(V0|V1)'")
    n.add_argument("--moderation", choices=["open", "approval"], default="open"); n.add_argument("--domain")
    n.add_argument("--auth", choices=["token", "kakao", "portone"], default="token", help="가입 방식 (기본 token=개발용)")
    n.add_argument("--portone-store-id"); n.add_argument("--portone-channel-key"); n.add_argument("--min-age", type=int, default=0)
    sub.add_parser("validate").set_defaults(fn=cmd_validate)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("serve"); s.set_defaults(fn=cmd_serve)
    s.add_argument("--host", default="0.0.0.0"); s.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(); a.fn(a)
