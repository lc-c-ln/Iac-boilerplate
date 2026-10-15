"""서비스 스펙: 주제(topic)와 객체(entities)를 선언하면 서비스가 된다."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

RESERVED = {"spec", "signup", "threads", "react", "records", "admin"}
FieldType = Literal["text", "longtext", "number", "select", "url", "bool"]


class FieldSpec(BaseModel):
    name: str
    type: FieldType = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    label: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.type == "select" and not self.options:
            raise ValueError(f"select 필드 '{self.name}'에는 options가 필요합니다")
        return self


class EntitySpec(BaseModel):
    key: str
    label: str
    fields: list[FieldSpec]
    title_field: str | None = None  # 목록에서 제목으로 쓸 필드 (기본: 첫 필드)

    @field_validator("key")
    @classmethod
    def _key(cls, v):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", v) or v in RESERVED:
            raise ValueError(f"잘못된 entity key: {v}")
        return v


class CommunitySpec(BaseModel):
    threads: bool = True            # 글/댓글
    reviews: bool = True            # 객체에 대한 별점 리뷰
    reactions: list[str] = ["like"]
    moderation: Literal["open", "approval"] = "open"  # approval: 등록 객체를 관리자가 승인


class PortOneSpec(BaseModel):
    store_id: str = ""        # 콘솔의 Store ID (공개 식별자)
    channel_key: str = ""     # 본인인증 채널 키 (공개 식별자)
    min_age: int = 0          # 만 나이 하한 (예: 19). 0이면 검사 안 함


class KakaoSpec(BaseModel):
    scope: list[str] = []     # 예: ["account_email"] (비즈 앱 검수 필요한 항목 주의)


class AuthSpec(BaseModel):
    provider: Literal["token", "kakao", "portone"] = "token"  # token: 개발/내부용 (handle만으로 가입)
    portone: PortOneSpec = PortOneSpec()
    kakao: KakaoSpec = KakaoSpec()

    @model_validator(mode="after")
    def _need(self):
        if self.provider == "portone" and not (self.portone.store_id and self.portone.channel_key):
            raise ValueError("auth.provider=portone 에는 portone.store_id / channel_key 가 필요합니다")
        return self


class ServiceSpec(BaseModel):
    slug: str
    name: str
    topic: str
    tagline: str = ""
    language: str = "ko"
    domain: str | None = None       # 커스텀 도메인(Host 헤더 매핑)
    theme: dict[str, str] = {"color": "#2563eb"}
    entities: list[EntitySpec]
    community: CommunitySpec = CommunitySpec()
    auth: AuthSpec = AuthSpec()

    @field_validator("slug")
    @classmethod
    def _slug(cls, v):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", v):
            raise ValueError("slug는 소문자/숫자/하이픈 2~41자")
        return v

    @model_validator(mode="after")
    def _uniq(self):
        keys = [e.key for e in self.entities]
        if len(keys) != len(set(keys)) or not keys:
            raise ValueError("entities는 1개 이상, key는 중복 불가")
        return self

    def entity(self, key: str) -> EntitySpec | None:
        return next((e for e in self.entities if e.key == key), None)


def validate_record(ent: EntitySpec, data: dict) -> dict:
    """스펙에 따라 레코드 검증/정규화. 위반 시 ValueError."""
    out, known = {}, {f.name for f in ent.fields}
    extra = set(data) - known
    if extra:
        raise ValueError(f"알 수 없는 필드: {sorted(extra)}")
    for f in ent.fields:
        v = data.get(f.name)
        if v in (None, ""):
            if f.required:
                raise ValueError(f"필수 필드 누락: {f.name}")
            continue
        if f.type == "number":
            try: v = float(v)
            except (TypeError, ValueError): raise ValueError(f"{f.name}: 숫자여야 함")
        elif f.type == "bool":
            if not isinstance(v, bool): raise ValueError(f"{f.name}: bool이어야 함")
        elif f.type == "select":
            if v not in f.options: raise ValueError(f"{f.name}: {f.options} 중 하나")
        elif f.type == "url":
            if not re.match(r"https?://", str(v)): raise ValueError(f"{f.name}: URL 형식 아님")
        else:
            v = str(v)[:5000 if f.type == "longtext" else 300]
        out[f.name] = v
    return out


def load_spec(path: Path) -> ServiceSpec:
    return ServiceSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class Registry:
    """specs/ 디렉터리를 감시. 파일을 추가/수정하면 재시작 없이 서비스가 생기거나 바뀐다."""

    def __init__(self, directory: Path):
        self.dir, self._cache = directory, {}

    def _scan(self):
        seen = {}
        for p in sorted(self.dir.glob("*.yaml")):
            if p.name.startswith("_"):
                continue
            m = p.stat().st_mtime
            if p in self._cache and self._cache[p][0] == m:
                seen[p] = self._cache[p]
                continue
            try: seen[p] = (m, load_spec(p))
            except Exception as e:
                print(f"[registry] {p.name} 무시됨: {e}")
        self._cache = seen

    def all(self) -> dict[str, ServiceSpec]:
        self._scan()
        return {s.slug: s for _, s in self._cache.values()}

    def get(self, slug: str) -> ServiceSpec | None:
        return self.all().get(slug)

    def by_host(self, host: str) -> ServiceSpec | None:
        host = host.split(":")[0]
        return next((s for s in self.all().values() if s.domain == host), None)
