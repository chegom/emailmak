# 시트 자동화 엔진 — Plan 1: 결정론적 코어 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 콜드메일 자동화 엔진의 외부 API 비의존 코어(설정·상태DB·크롤러 호환·이메일 검증·중복제거)를 TDD로 구축한다.

**Architecture:** OAuth/멀티유저 진행작업(`app/`)과 완전히 분리된 `engine/` 패키지를 새로 만든다. 모든 서비스는 SQLAlchemy `Session`을 주입받아 외부 의존 없이 단위 테스트된다. 상태는 별도 `state.db`(SQLite)에 저장하며 `app/config`(OAuth 필수)에 의존하지 않는다.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0, pydantic-settings, dnspython, pytest / pytest-asyncio.

**선행 스펙:** `docs/superpowers/specs/2026-06-01-sheet-driven-smartlead-automation-design.md`
**다음 계획(Plan 2):** SheetControl · GeminiClient/KeywordResolver · SchedulePlanner · SmartleadClient · AlertMonitor · HourlyTick · 배포.

---

## File Structure (Plan 1 범위)

| 파일 | 책임 |
|------|------|
| `engine/__init__.py` | 패키지 마커 |
| `engine/settings.py` | `EngineSettings` — OAuth 비의존 환경설정 |
| `engine/db.py` | state.db 엔진/세션 팩토리 (`app/db`와 별개) |
| `engine/models.py` | `EngineState`/`PushedEmail`/`MxCache`/`RunLock` ORM |
| `engine/validator.py` | `EmailValidator` — 문법+시스템주소/일회용 제외+MX(캐시) |
| `engine/dedup.py` | `DedupStore` — accepted만 기준 중복제거 |
| `crawlers/wanted.py` | (수정) `crawl_with_emails()` 추가 — 호환 크래시 해결 |
| `tests/engine/conftest.py` | in-memory state.db 세션 픽스처 |
| `tests/engine/test_*.py` | 각 단위 테스트 |

**원칙:** 서비스는 `Session`을 인자로 받는다(모듈 전역 세션 사용 금지) → 테스트 격리. `engine/`는 `app/`을 import 하지 않는다.

---

## Task 1: EngineSettings (OAuth 비의존 설정)

**Files:**
- Create: `engine/__init__.py`
- Create: `engine/settings.py`
- Test: `tests/engine/__init__.py`, `tests/engine/test_settings.py`

- [ ] **Step 1: 빈 패키지 마커 생성**

Create `engine/__init__.py` (빈 파일) 와 `tests/engine/__init__.py` (빈 파일).

- [ ] **Step 2: 실패하는 테스트 작성**

Create `tests/engine/test_settings.py`:

```python
import importlib
import os

import pytest


def _fresh_settings(monkeypatch, **env):
    # OAuth 관련 env는 일부러 비운다 — 엔진은 이것에 의존하면 안 됨
    for k in ("APP_SECRET_KEY", "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import engine.settings as s
    importlib.reload(s)
    s.get_engine_settings.cache_clear()
    return s.get_engine_settings()


def test_loads_without_oauth_env(monkeypatch):
    cfg = _fresh_settings(
        monkeypatch,
        SMARTLEAD_API_KEY="sl-key",
        GEMINI_API_KEY="gm-key",
        CONTROL_SHEET_URL="https://docs.google.com/x",
        GOOGLE_CREDENTIALS_JSON="{}",
    )
    assert cfg.smartlead_api_key == "sl-key"
    assert cfg.gemini_api_key == "gm-key"
    assert cfg.control_sheet_url.endswith("/x")


def test_threshold_defaults(monkeypatch):
    cfg = _fresh_settings(
        monkeypatch,
        SMARTLEAD_API_KEY="x", GEMINI_API_KEY="x",
        CONTROL_SHEET_URL="x", GOOGLE_CREDENTIALS_JSON="{}",
    )
    assert cfg.bounce_warn == 0.05
    assert cfg.bounce_critical == 0.08
    assert cfg.min_bounce_sample == 50
    assert cfg.min_pass_rate == 0.40
    assert cfg.smartlead_daily_limit == 200
    assert cfg.state_db_url == "sqlite:///./data/state.db"


def test_required_field_missing_raises(monkeypatch):
    with pytest.raises(Exception):
        _fresh_settings(monkeypatch, GEMINI_API_KEY="x",
                        CONTROL_SHEET_URL="x", GOOGLE_CREDENTIALS_JSON="{}")
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `pytest tests/engine/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.settings'`

- [ ] **Step 4: 최소 구현**

Create `engine/settings.py`:

```python
"""엔진 전용 설정. app/config(OAuth 필수)와 분리되어 OAuth env 없이 부팅된다."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class EngineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 필수 — 엔진 동작에 반드시 필요
    smartlead_api_key: str
    gemini_api_key: str
    control_sheet_url: str
    google_credentials_json: str

    # 선택 — 임계치/한도 (스펙 §9 기본값)
    bounce_warn: float = 0.05
    bounce_critical: float = 0.08
    min_bounce_sample: int = 50
    min_pass_rate: float = 0.40
    smartlead_daily_limit: int = 200

    # 상태 저장소 — app/config의 database_url과 별개
    state_db_url: str = "sqlite:///./data/state.db"


@lru_cache(maxsize=1)
def get_engine_settings() -> EngineSettings:
    return EngineSettings()  # type: ignore[call-arg]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `pytest tests/engine/test_settings.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 커밋**

```bash
git add engine/__init__.py engine/settings.py tests/engine/__init__.py tests/engine/test_settings.py
git commit -m "feat(engine): EngineSettings — OAuth 비의존 환경설정"
```

---

## Task 2: state.db 스키마 + 엔진 DB 세션

**Files:**
- Create: `engine/db.py`
- Create: `engine/models.py`
- Create: `tests/engine/conftest.py`
- Test: `tests/engine/test_models.py`

- [ ] **Step 1: 세션 픽스처 작성**

Create `tests/engine/conftest.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from engine.db import Base
import engine.models  # noqa: F401  — 모델을 메타데이터에 등록


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 동일 in-memory DB를 모든 연결이 공유
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()
```

- [ ] **Step 2: 실패하는 테스트 작성**

Create `tests/engine/test_models.py`:

```python
from engine.models import EngineState, PushedEmail, MxCache, RunLock


def test_engine_state_roundtrip(session):
    session.add(EngineState(key="suspended:123", value="1"))
    session.commit()
    row = session.get(EngineState, "suspended:123")
    assert row.value == "1"


def test_pushed_email_unique(session):
    session.add(PushedEmail(email="a@x.com", domain="x.com", campaign_id="123"))
    session.commit()
    assert session.get(PushedEmail, "a@x.com").domain == "x.com"


def test_mx_cache_roundtrip(session):
    session.add(MxCache(domain="x.com", mx_valid=True))
    session.commit()
    assert session.get(MxCache, "x.com").mx_valid is True


def test_run_lock_roundtrip(session):
    session.add(RunLock(row_key="물류|2026-06-04 09:00"))
    session.commit()
    assert session.get(RunLock, "물류|2026-06-04 09:00") is not None
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `pytest tests/engine/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.db'`

- [ ] **Step 4: db.py 구현**

Create `engine/db.py`:

```python
"""엔진 상태 DB(state.db) 엔진/세션. app/db와 독립 — app.config(OAuth) import 안 함."""
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)


# EngineSettings 전체(시크릿 필수)를 구성하지 않고 DB URL만 직접 읽어 디커플링.
STATE_DB_URL = os.getenv("STATE_DB_URL", "sqlite:///./data/state.db")
_ensure_sqlite_dir(STATE_DB_URL)

engine = create_engine(
    STATE_DB_URL,
    connect_args={"check_same_thread": False} if STATE_DB_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    if STATE_DB_URL.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA busy_timeout=5000;")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 5: models.py 구현**

Create `engine/models.py`:

```python
"""state.db ORM 모델 (스펙 §4.2)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from engine.db import Base


class EngineState(Base):
    __tablename__ = "engine_state"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class PushedEmail(Base):
    __tablename__ = "pushed_emails"
    email: Mapped[str] = mapped_column(String, primary_key=True)  # 정규화(소문자)
    domain: Mapped[str] = mapped_column(String, index=True)
    campaign_id: Mapped[str] = mapped_column(String)
    pushed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MxCache(Base):
    __tablename__ = "mx_cache"
    domain: Mapped[str] = mapped_column(String, primary_key=True)
    mx_valid: Mapped[bool] = mapped_column(Boolean)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RunLock(Base):
    __tablename__ = "run_lock"
    row_key: Mapped[str] = mapped_column(String, primary_key=True)  # 산업군|예정일시
    locked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `pytest tests/engine/test_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: 커밋**

```bash
git add engine/db.py engine/models.py tests/engine/conftest.py tests/engine/test_models.py
git commit -m "feat(engine): state.db 세션 + EngineState/PushedEmail/MxCache/RunLock 모델"
```

---

## Task 3: WantedCrawler.crawl_with_emails (호환 크래시 수정)

**배경:** `server.py:108`은 모든 크롤러에 `crawl_with_emails()`가 있다고 가정하지만 `crawlers/wanted.py`엔 없어 wanted 선택 시 `AttributeError` 크래시. saramin/jobkorea 시그니처와 동일하게 추가한다. wanted는 `get_company_detail`에 `api_id`를 넘긴다(상세 §3 컴포넌트).

**Files:**
- Modify: `crawlers/wanted.py` (클래스 끝에 메서드 추가)
- Test: `tests/test_wanted_crawl.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/test_wanted_crawl.py`:

```python
import pytest

from crawlers.wanted import WantedCrawler


@pytest.mark.asyncio
async def test_crawl_with_emails_uses_api_id_and_sorts(monkeypatch):
    crawler = WantedCrawler()

    async def fake_search(keyword, start_page=1, end_page=5):
        return [
            {"company_name": "A", "company_url": "u/1", "api_id": "1",
             "job_url": None, "job_title": "A 채용", "homepage": None, "emails": []},
            {"company_name": "B", "company_url": "u/2", "api_id": "2",
             "job_url": None, "job_title": "B 채용", "homepage": None, "emails": []},
        ]

    async def fake_detail(api_id):
        return {"homepage": f"http://site-{api_id}.com"}

    async def fake_extract(url):
        # A(api_id=1) → 이메일 0개, B(api_id=2) → 1개  → B가 앞으로 정렬돼야 함
        return ["b@site-2.com"] if "site-2" in url else []

    monkeypatch.setattr(crawler, "search", fake_search)
    monkeypatch.setattr(crawler, "get_company_detail", fake_detail)
    monkeypatch.setattr(crawler.email_extractor, "extract_from_url", fake_extract)

    result = await crawler.crawl_with_emails("물류", 1, 1)

    assert result[0]["company_name"] == "B"
    assert result[0]["emails"] == ["b@site-2.com"]
    assert result[1]["emails"] == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_wanted_crawl.py -v`
Expected: FAIL — `AttributeError: 'WantedCrawler' object has no attribute 'crawl_with_emails'`

- [ ] **Step 3: 메서드 구현**

`crawlers/wanted.py` 의 `fetch_json` 메서드 다음(클래스 본문 끝)에 추가. 상단 `import asyncio`는 이미 존재한다.

```python
    async def crawl_with_emails(self, keyword: str, start_page: int = 1, end_page: int = 5,
                                 progress_callback=None) -> List[Dict[str, Any]]:
        """검색 → 상세(홈페이지) → 이메일 추출. saramin/jobkorea와 동일 시그니처."""
        companies = await self.search(keyword, start_page, end_page)
        total = len(companies)
        print(f"[INFO] Wanted: {total} companies (pages {start_page}-{end_page}). Extracting emails...")

        for idx, company in enumerate(companies):
            try:
                if progress_callback:
                    progress_callback(idx + 1, total, company["company_name"])

                # wanted는 상세 조회에 api_id 사용 (company_url 아님)
                detail = await self.get_company_detail(company.get("api_id") or company["company_url"])
                company["homepage"] = detail.get("homepage")

                if company["homepage"]:
                    company["emails"] = await self.email_extractor.extract_from_url(company["homepage"])

                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"[ERROR] Failed to process {company['company_name']}: {e}")
                continue

        companies.sort(key=lambda x: len(x.get("emails", [])), reverse=True)
        return companies
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_wanted_crawl.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 커밋**

```bash
git add crawlers/wanted.py tests/test_wanted_crawl.py
git commit -m "fix(crawler): WantedCrawler.crawl_with_emails 추가 — /api/crawl wanted 크래시 해결"
```

---

## Task 4: EmailValidator (문법 + 시스템주소/일회용 제외 + MX 캐시)

**정책(스펙 §2):** 시스템주소(`no-reply@` 등)·일회용 도메인·문법오류·MX없음 → 제외. 역할주소(`recruit@ hr@ info@ …`)는 **포함하되 `is_role=True` 표시**. MX 조회는 dnspython, 결과는 `mx_cache`에 7일 캐시. 테스트 격리를 위해 MX 조회 함수는 주입 가능.

**Files:**
- Create: `engine/validator.py`
- Modify: `requirements.txt` (dnspython 추가)
- Test: `tests/engine/test_validator.py`

- [ ] **Step 1: requirements.txt에 dnspython 추가**

`requirements.txt` 의 `lxml==5.3.0` 다음 줄에 추가:

```
dnspython==2.6.1
```

Run: `pip install dnspython==2.6.1`

- [ ] **Step 2: 실패하는 테스트 작성**

Create `tests/engine/test_validator.py`:

```python
from datetime import datetime, timedelta

from engine.models import MxCache
from engine.validator import EmailValidator, EmailStatus


def make_validator(session, mx_ok=True):
    # MX 조회를 가짜로 — 모든 도메인 mx_ok 반환
    return EmailValidator(session, mx_lookup=lambda domain: mx_ok)


def company(name, emails):
    return {"company_name": name, "emails": emails, "job_title": "t",
            "source": "wanted", "homepage": "h", "company_url": "c"}


def test_syntax_invalid_dropped(session):
    v = make_validator(session)
    res = v.validate([company("A", ["not-an-email", "good@valid.com"])])
    emails = {r["email"] for r in res.valid}
    assert emails == {"good@valid.com"}
    assert any(d["reason"] == "syntax" for d in res.dropped)


def test_system_address_dropped(session):
    v = make_validator(session)
    res = v.validate([company("A", ["no-reply@valid.com", "postmaster@valid.com"])])
    assert res.valid == []
    assert all(d["reason"] == "system" for d in res.dropped)


def test_disposable_domain_dropped(session):
    v = make_validator(session)
    res = v.validate([company("A", ["x@mailinator.com"])])
    assert res.valid == []
    assert res.dropped[0]["reason"] == "disposable"


def test_role_address_kept_and_flagged(session):
    v = make_validator(session)
    res = v.validate([company("A", ["recruit@valid.com", "ceo@valid.com"])])
    by_email = {r["email"]: r for r in res.valid}
    assert by_email["recruit@valid.com"]["is_role"] is True
    assert by_email["ceo@valid.com"]["is_role"] is False


def test_mx_missing_dropped(session):
    v = make_validator(session, mx_ok=False)
    res = v.validate([company("A", ["x@nomx.com"])])
    assert res.valid == []
    assert res.dropped[0]["reason"] == "no_mx"


def test_mx_cache_hit_skips_lookup(session):
    calls = []
    v = EmailValidator(session, mx_lookup=lambda d: calls.append(d) or True)
    session.add(MxCache(domain="cached.com", mx_valid=True, checked_at=datetime.utcnow()))
    session.commit()
    v.validate([company("A", ["x@cached.com"])])
    assert calls == []  # 캐시 적중 → 조회 안 함


def test_pass_rate(session):
    v = make_validator(session)
    res = v.validate([company("A", ["good@valid.com", "bad"])])
    assert res.pass_rate == 0.5
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `pytest tests/engine/test_validator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.validator'`

- [ ] **Step 4: validator.py 구현**

Create `engine/validator.py`:

```python
"""이메일 검증: 문법 + 시스템주소/일회용 제외 + MX(캐시). SMTP RCPT 안 함(포트25 차단)."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from engine.models import MxCache

_SYNTAX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MX_TTL = timedelta(days=7)

# 발송하면 안 되는 시스템 주소 → 제외
SYSTEM_LOCALPARTS = {
    "no-reply", "noreply", "donotreply", "do-not-reply",
    "postmaster", "mailer-daemon", "abuse", "bounce", "bounces",
}
# 업무용 역할 주소 → 포함하되 표시
ROLE_LOCALPARTS = {
    "info", "sales", "contact", "recruit", "hr", "jobs",
    "support", "admin", "help", "marketing", "career", "careers",
}
DISPOSABLE_DOMAINS = {
    "mailinator.com", "10minutemail.com", "guerrillamail.com",
    "tempmail.com", "trashmail.com", "yopmail.com",
}


def default_mx_lookup(domain: str) -> bool:
    import dns.resolver  # 지연 import
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return len(answers) > 0
    except Exception:
        return False


@dataclass
class ValidationResult:
    valid: list = field(default_factory=list)     # {company_name, email, domain, is_role, job_title, source}
    dropped: list = field(default_factory=list)   # {email, reason}

    @property
    def pass_rate(self) -> float:
        total = len(self.valid) + len(self.dropped)
        return len(self.valid) / total if total else 0.0


class EmailStatus:
    PASS = "pass"
    ROLE = "role"


class EmailValidator:
    def __init__(self, session: Session, mx_lookup: Callable[[str], bool] = default_mx_lookup):
        self.session = session
        self.mx_lookup = mx_lookup

    def _mx_valid(self, domain: str) -> bool:
        row = self.session.get(MxCache, domain)
        if row and (datetime.utcnow() - row.checked_at) < _MX_TTL:
            return row.mx_valid
        valid = self.mx_lookup(domain)
        if row:
            row.mx_valid = valid
            row.checked_at = datetime.utcnow()
        else:
            self.session.add(MxCache(domain=domain, mx_valid=valid, checked_at=datetime.utcnow()))
        self.session.commit()
        return valid

    def validate(self, companies: list) -> ValidationResult:
        res = ValidationResult()
        for c in companies:
            for email in c.get("emails", []):
                email = (email or "").strip().lower()
                if not _SYNTAX.match(email):
                    res.dropped.append({"email": email, "reason": "syntax"})
                    continue
                local, domain = email.split("@", 1)
                if local in SYSTEM_LOCALPARTS:
                    res.dropped.append({"email": email, "reason": "system"})
                    continue
                if domain in DISPOSABLE_DOMAINS:
                    res.dropped.append({"email": email, "reason": "disposable"})
                    continue
                if not self._mx_valid(domain):
                    res.dropped.append({"email": email, "reason": "no_mx"})
                    continue
                res.valid.append({
                    "company_name": c.get("company_name"),
                    "email": email,
                    "domain": domain,
                    "is_role": local in ROLE_LOCALPARTS,
                    "job_title": c.get("job_title"),
                    "source": c.get("source"),
                })
        return res
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `pytest tests/engine/test_validator.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: 커밋**

```bash
git add engine/validator.py requirements.txt tests/engine/test_validator.py
git commit -m "feat(engine): EmailValidator — 문법+시스템/일회용 제외+MX 캐시, 역할주소 표시"
```

---

## Task 5: DedupStore (accepted만 기준 중복제거)

**핵심(리스크 #1 해결):** dedup 기준은 **실제 푸시 성공(accepted)** 이메일뿐. suspended/failed는 등록하지 않아 다음 실행에서 재시도된다.

**Files:**
- Create: `engine/dedup.py`
- Test: `tests/engine/test_dedup.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/engine/test_dedup.py`:

```python
from engine.dedup import DedupStore
from engine.models import PushedEmail


def rec(email, **kw):
    d = {"email": email, "domain": email.split("@")[1]}
    d.update(kw)
    return d


def test_filter_new_excludes_already_pushed(session):
    session.add(PushedEmail(email="old@x.com", domain="x.com", campaign_id="1"))
    session.commit()
    store = DedupStore(session)
    fresh = store.filter_new([rec("old@x.com"), rec("new@x.com")])
    assert [r["email"] for r in fresh] == ["new@x.com"]


def test_filter_new_normalizes_case(session):
    session.add(PushedEmail(email="a@x.com", domain="x.com", campaign_id="1"))
    session.commit()
    store = DedupStore(session)
    fresh = store.filter_new([rec("A@X.com")])
    assert fresh == []  # 대소문자 무시


def test_mark_pushed_records_accepted_only(session):
    store = DedupStore(session)
    store.mark_pushed([rec("a@x.com"), rec("b@y.com")], campaign_id="42")
    assert session.get(PushedEmail, "a@x.com").campaign_id == "42"
    assert session.get(PushedEmail, "b@y.com") is not None


def test_mark_pushed_is_idempotent(session):
    store = DedupStore(session)
    store.mark_pushed([rec("a@x.com")], campaign_id="1")
    store.mark_pushed([rec("a@x.com")], campaign_id="1")  # 중복 호출 시 예외 없어야
    assert session.query(PushedEmail).count() == 1


def test_backfill_inserts_accepted(session):
    store = DedupStore(session)
    store.backfill([rec("a@x.com", campaign_id="9"), rec("b@y.com", campaign_id="9")])
    assert session.query(PushedEmail).count() == 2
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/engine/test_dedup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.dedup'`

- [ ] **Step 3: dedup.py 구현**

Create `engine/dedup.py`:

```python
"""중복제거: accepted(실제 푸시 성공) 이메일만 기준. suspended/failed는 미등록 → 재시도 가능."""
from sqlalchemy.orm import Session

from engine.models import PushedEmail


def _norm(email: str) -> str:
    return (email or "").strip().lower()


class DedupStore:
    def __init__(self, session: Session):
        self.session = session

    def _already(self, email: str) -> bool:
        return self.session.get(PushedEmail, _norm(email)) is not None

    def filter_new(self, records: list) -> list:
        """records: [{email, domain, ...}] → 아직 푸시 안 된 것만 반환."""
        return [r for r in records if not self._already(r["email"])]

    def mark_pushed(self, records: list, campaign_id: str) -> None:
        """accepted 레코드만 호출할 것."""
        for r in records:
            email = _norm(r["email"])
            if self.session.get(PushedEmail, email):  # 멱등
                continue
            self.session.add(PushedEmail(
                email=email,
                domain=r.get("domain") or email.split("@", 1)[-1],
                campaign_id=campaign_id,
            ))
        self.session.commit()

    def backfill(self, records: list) -> None:
        """발송내역 시트의 accepted 행으로 부팅 시 1회 복구 (campaign_id 포함)."""
        for r in records:
            email = _norm(r["email"])
            if self.session.get(PushedEmail, email):
                continue
            self.session.add(PushedEmail(
                email=email,
                domain=r.get("domain") or email.split("@", 1)[-1],
                campaign_id=r.get("campaign_id", ""),
            ))
        self.session.commit()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/engine/test_dedup.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 전체 엔진 테스트 회귀 확인**

Run: `pytest tests/engine -v`
Expected: PASS (전체 통과 — settings 3 + models 4 + validator 7 + dedup 5)

- [ ] **Step 6: 커밋**

```bash
git add engine/dedup.py tests/engine/test_dedup.py
git commit -m "feat(engine): DedupStore — accepted만 기준 중복제거 + backfill"
```

---

## Plan 1 완료 기준

- [ ] `pytest tests/engine tests/test_wanted_crawl.py -v` 전체 통과
- [ ] `engine/` 어떤 모듈도 `app/` 을 import 하지 않음 (`grep -rn "import app" engine/` → 결과 없음)
- [ ] OAuth env 없이 `STATE_DB_URL=sqlite:///:memory: python -c "import engine.db, engine.models, engine.validator, engine.dedup"` 성공
- [ ] wanted 포함 3사 크롤러가 동일하게 `crawl_with_emails()` 보유

이 시점에서 **외부 API 없이 동작·테스트되는 코어**가 완성된다. Plan 2에서 SheetControl·Gemini·SmartleadClient·SchedulePlanner·AlertMonitor·HourlyTick으로 이들을 조립하고 배포한다.
</content>
