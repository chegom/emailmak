# Plan 1: Foundation + Auth + Onboarding 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 익명 크롤링 기능을 회귀 없이 유지한 채, Google OAuth 로그인 + 멀티유저 기반 + 시크릿 암호 저장 + 온보딩 UI를 도입한다. 새 비즈니스 기능은 추가하지 않고, 후속 plan(품질 파이프라인, 스케줄링)의 토대만 완성한다.

**Architecture:** `server.py`에 모여 있던 라우트를 `app/<feature>/router.py`로 분리하고, SQLAlchemy + alembic으로 DB를 도입한다. Google OAuth(authlib)로 로그인 후 `itsdangerous` 서명 쿠키로 세션을 관리한다. Smartlead 키는 `cryptography.fernet`로 암호화하여 저장한다. 익명 라우트는 그대로 유지하고, 신규 라우트만 `Depends(require_login)`로 보호한다.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, alembic, authlib, itsdangerous, cryptography, pytest, httpx (TestClient), respx, freezegun.

---

## 디렉터리 / 파일 구조 (Plan 1 종료 시점)

```
emailmak-main/
├── server.py                       # 슬림 엔트리: app factory 호출, uvicorn
├── app/
│   ├── __init__.py
│   ├── factory.py                  # create_app() — 라우터/미들웨어 등록
│   ├── config.py                   # 환경변수 → Settings (pydantic-settings)
│   ├── db.py                       # SQLAlchemy engine, get_session
│   ├── models.py                   # ORM 모델 (Plan 1 범위: User만)
│   ├── crypto.py                   # Fernet 암호화 유틸
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── router.py               # /api/auth/start, /callback, /logout
│   │   ├── oauth.py                # Google OAuth 클라이언트 래퍼
│   │   ├── session.py              # 쿠키 read/write 헬퍼
│   │   ├── whitelist.py            # 도메인/이메일 화이트리스트 검사
│   │   └── deps.py                 # require_login, get_current_user FastAPI deps
│   ├── users/
│   │   ├── __init__.py
│   │   ├── router.py               # /api/users/me, /api/users/onboard
│   │   ├── schemas.py              # Pydantic 요청·응답 모델
│   │   └── service.py              # upsert_from_oauth, save_onboarding
│   └── crawl/
│       ├── __init__.py
│       └── router.py               # /api/crawl, /api/crawl/stream, /api/export/sheet, /api/config/google-sheet, /api/debug/jobkorea, /
├── crawlers/                       # (기존 그대로)
├── utils/                          # (기존 그대로)
├── static/
│   ├── index.html                  # 헤더에 "시작하기" 버튼 추가
│   ├── onboarding.html             # 신규 — 시트 URL + Smartlead 키 입력
│   ├── app.js                      # 로그인 상태 표시·온보딩 리다이렉트
│   ├── onboarding.js               # 신규
│   └── style.css                   # (기존 + 헤더 보강)
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_users.py
├── data/                           # 런타임 생성 (gitignore에 추가)
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_crypto.py
│   ├── test_whitelist.py
│   ├── test_auth_flow.py
│   ├── test_users_router.py
│   ├── test_crawl_regression.py
│   └── fixtures/
│       └── oauth_responses.py
├── requirements.txt                # 의존성 추가
└── .gitignore                      # data/, *.db, .env 등 추가
```

후속 plan에서 추가될 모듈(`schedule/`, `blacklist/`, `validate/`, `smartlead/`, `workers/`)은 본 plan 범위 밖. `models.py`는 Plan 2/3에서 점진 확장.

---

## Task 0: Git 초기화 + .gitignore + 의존성

**Files:**
- Create: `.gitignore`
- Modify: `requirements.txt`

- [ ] **Step 1: 현재 디렉터리가 git 저장소가 아니므로 초기화**

```bash
cd /Users/uhuru/dev/emailmak-main
git init
git add -A
git status
```

Expected: 모든 기존 파일이 untracked로 표시.

- [ ] **Step 2: `.gitignore` 작성**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.venv/
venv/

# App data
data/
*.db
*.db-journal
*.db-wal
*.db-shm

# Env / secrets
.env
.env.*
!.env.example

# OS
.DS_Store
```

- [ ] **Step 3: `requirements.txt` 의존성 추가**

기존 파일에 다음 라인을 추가 (정렬은 유지):

```
fastapi==0.109.0
uvicorn==0.27.0
httpx==0.26.0
beautifulsoup4==4.12.3
lxml==5.3.0
gspread==6.0.0
sqlalchemy==2.0.30
alembic==1.13.2
authlib==1.3.2
itsdangerous==2.2.0
cryptography==43.0.1
pydantic-settings==2.5.2
python-multipart==0.0.9
pytest==8.3.3
pytest-asyncio==0.24.0
respx==0.21.1
freezegun==1.5.1
```

- [ ] **Step 4: 가상환경 + 설치 확인**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "import fastapi, sqlalchemy, alembic, authlib, cryptography, pytest; print('OK')"
```

Expected: `OK` 출력. 에러 발생 시 OS별 의존성 문제 점검.

- [ ] **Step 5: 초기 커밋**

```bash
git add .gitignore requirements.txt
git add -A    # 기존 파일들도 모두 커밋
git commit -m "chore: initial commit + project deps"
```

---

## Task 1: 설정(Settings) 모듈

**Files:**
- Create: `app/__init__.py` (빈 파일)
- Create: `app/config.py`
- Create: `tests/__init__.py` (빈 파일)
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: 테스트 먼저 작성 — `tests/test_config.py`**

```python
import os
import pytest


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key-please-rotate")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret-abc")
    monkeypatch.setenv("ALLOWED_OAUTH_DOMAIN", "example.com,test.com")
    monkeypatch.setenv("ALLOWED_OAUTH_EMAILS", "alice@external.com")

    # 인메모리 리로드를 위해 모듈을 강제로 다시 import
    from importlib import reload
    from app import config as config_module
    reload(config_module)

    s = config_module.get_settings()
    assert s.app_secret_key == "test-secret-key-please-rotate"
    assert s.database_url.endswith("test.db")
    assert s.google_oauth_client_id == "client-id-123"
    assert s.allowed_oauth_domains == ["example.com", "test.com"]
    assert s.allowed_oauth_emails == ["alice@external.com"]


def test_settings_defaults_when_optional_unset(monkeypatch):
    for k in ["ALLOWED_OAUTH_DOMAIN", "ALLOWED_OAUTH_EMAILS"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "cs")

    from importlib import reload
    from app import config as config_module
    reload(config_module)

    s = config_module.get_settings()
    assert s.allowed_oauth_domains == []
    assert s.allowed_oauth_emails == []


def test_settings_missing_required_raises(monkeypatch):
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)

    from importlib import reload
    from app import config as config_module
    reload(config_module)

    with pytest.raises(Exception):
        config_module.get_settings()
```

- [ ] **Step 2: `tests/conftest.py` 작성 — pytest 공통 설정**

```python
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가하여 `app.` 임포트 가능하게
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 테스트 환경 기본값
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-32bytes-minimum-x")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
```

- [ ] **Step 3: 실패 확인**

```bash
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 4: `app/__init__.py` 와 `tests/__init__.py` 빈 파일 생성**

둘 다 빈 파일.

- [ ] **Step 5: `app/config.py` 구현**

```python
"""
애플리케이션 설정. 환경변수에서 값을 읽어 Settings 객체로 노출.
"""
from functools import lru_cache
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 필수
    app_secret_key: str
    google_oauth_client_id: str
    google_oauth_client_secret: str

    # 선택 (기본값 있음)
    database_url: str = "sqlite:///./data/app.db"
    allowed_oauth_domain: str = ""
    allowed_oauth_emails: str = ""

    # 외부 노출용 파생 필드
    @property
    def allowed_oauth_domains(self) -> List[str]:
        return [d.strip() for d in self.allowed_oauth_domain.split(",") if d.strip()]

    @property
    def allowed_oauth_emails_list(self) -> List[str]:
        return [e.strip().lower() for e in self.allowed_oauth_emails.split(",") if e.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 6: 테스트의 `allowed_oauth_emails` 단언 정렬**

테스트에서 `s.allowed_oauth_emails` 대신 `s.allowed_oauth_emails_list`를 호출하도록 수정한다 (Step 1의 테스트 코드와 일치하지 않는다면 테스트를 갱신):

```python
# tests/test_config.py 에서 두 군데 수정:
assert s.allowed_oauth_emails_list == ["alice@external.com"]
# ...
assert s.allowed_oauth_emails_list == []
```

- [ ] **Step 7: 통과 확인**

```bash
pytest tests/test_config.py -v
```

Expected: 3 passed.

- [ ] **Step 8: 커밋**

```bash
git add app/__init__.py app/config.py tests/__init__.py tests/conftest.py tests/test_config.py
git commit -m "feat(config): add Settings module loading env vars"
```

---

## Task 2: Fernet 암호화 유틸

**Files:**
- Create: `app/crypto.py`
- Create: `tests/test_crypto.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/test_crypto.py`**

```python
import pytest
from app.crypto import encrypt_secret, decrypt_secret, mask_secret


def test_encrypt_decrypt_roundtrip():
    plain = "sk-smartlead-abcdef1234567890"
    cipher = encrypt_secret(plain)
    assert cipher != plain
    assert decrypt_secret(cipher) == plain


def test_encrypt_produces_different_ciphertexts_each_call():
    plain = "the-same-secret"
    c1 = encrypt_secret(plain)
    c2 = encrypt_secret(plain)
    assert c1 != c2  # Fernet은 IV가 매번 달라 평문 같아도 ciphertext 다름
    assert decrypt_secret(c1) == decrypt_secret(c2) == plain


def test_decrypt_garbage_raises():
    with pytest.raises(Exception):
        decrypt_secret("not-a-valid-fernet-token")


def test_mask_keeps_prefix_and_suffix():
    assert mask_secret("sk-abcdefghijklmnop") == "sk-a***mnop"
    assert mask_secret("short") == "***"   # 8자 미만은 전부 마스크
    assert mask_secret("") == ""
    assert mask_secret(None) == ""
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_crypto.py -v
```

Expected: ImportError.

- [ ] **Step 3: `app/crypto.py` 구현**

```python
"""
시크릿 암호화·마스킹 유틸.
APP_SECRET_KEY를 시드로 PBKDF2-HMAC-SHA256으로 Fernet 키 파생.
"""
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet

from app.config import get_settings


_FERNET: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is None:
        seed = get_settings().app_secret_key.encode("utf-8")
        # 32바이트로 파생 후 base64로 인코딩 (Fernet 요구 사항)
        key = hashlib.pbkdf2_hmac("sha256", seed, b"emailmak-fernet-v1", 100_000, dklen=32)
        _FERNET = Fernet(base64.urlsafe_b64encode(key))
    return _FERNET


def encrypt_secret(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def mask_secret(value: Optional[str]) -> str:
    if not value:
        return ""
    if len(value) < 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"
```

- [ ] **Step 4: 통과 확인**

```bash
pytest tests/test_crypto.py -v
```

Expected: 4 passed.

- [ ] **Step 5: 커밋**

```bash
git add app/crypto.py tests/test_crypto.py
git commit -m "feat(crypto): Fernet encrypt/decrypt + secret masking"
```

---

## Task 3: SQLAlchemy 엔진 + Session 의존성

**Files:**
- Create: `app/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/test_db.py`**

```python
from app.db import engine, get_session, Base
from sqlalchemy import text


def test_engine_uses_settings_url():
    assert "sqlite" in str(engine.url)


def test_get_session_yields_usable_session():
    gen = get_session()
    session = next(gen)
    try:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_base_metadata_available():
    assert hasattr(Base, "metadata")
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_db.py -v
```

Expected: ImportError on `app.db`.

- [ ] **Step 3: `app/db.py` 구현**

```python
"""
DB 엔진·세션 관리.
SQLite WAL 모드 + busy_timeout 5초 (디자인 문서 7절).
"""
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        db_path = Path(url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)


_settings = get_settings()
_ensure_sqlite_dir(_settings.database_url)

engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_pragmas(dbapi_conn, _):
    if _settings.database_url.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA busy_timeout=5000;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI Depends용 세션 generator."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """워커·스크립트용 컨텍스트 매니저."""
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

- [ ] **Step 4: 통과 확인**

```bash
pytest tests/test_db.py -v
```

Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat(db): SQLAlchemy engine + session factory with SQLite pragmas"
```

---

## Task 4: User 모델 + alembic 초기 마이그레이션

**Files:**
- Create: `app/models.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial_users.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: 모델 테스트 작성 — `tests/test_models.py`**

```python
from datetime import datetime
from sqlalchemy import inspect

from app.db import engine, Base, SessionLocal
from app.models import User


def setup_module(_):
    Base.metadata.create_all(bind=engine)


def teardown_module(_):
    Base.metadata.drop_all(bind=engine)


def test_user_table_columns():
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("users")}
    assert {"id", "google_sub", "email", "name", "sheet_url", "smartlead_key",
            "created_at", "last_login_at"}.issubset(cols)


def test_user_unique_constraint_on_google_sub():
    s = SessionLocal()
    try:
        s.add(User(google_sub="g-1", email="a@x.com", name="A"))
        s.commit()
        s.add(User(google_sub="g-1", email="b@x.com", name="B"))
        try:
            s.commit()
            raise AssertionError("expected IntegrityError")
        except Exception:
            s.rollback()
    finally:
        s.close()


def test_user_defaults_created_at_now():
    s = SessionLocal()
    try:
        u = User(google_sub="g-now", email="now@x.com", name="N")
        s.add(u)
        s.commit()
        s.refresh(u)
        assert isinstance(u.created_at, datetime)
    finally:
        s.close()
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_models.py -v
```

Expected: ImportError on `app.models.User`.

- [ ] **Step 3: `app/models.py` 구현 (Plan 1은 User만)**

```python
"""
ORM 모델.
Plan 1 범위: User. (schedule_jobs, blacklist 등은 Plan 2/3에서 추가.)
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_sub: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sheet_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    smartlead_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 암호화된 토큰
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 4: 모델 테스트 통과 확인**

```bash
pytest tests/test_models.py -v
```

Expected: 3 passed.

- [ ] **Step 5: `alembic.ini` 생성**

```ini
[alembic]
script_location = alembic
sqlalchemy.url = sqlite:///./data/app.db
file_template = %%(rev)s_%%(slug)s

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 6: `alembic/env.py` 작성**

```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from app.config import get_settings
from app.db import Base
import app.models  # noqa: F401 — 모든 모델 메타데이터를 등록

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite ALTER 제약 우회
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 7: `alembic/script.py.mako` 생성**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    ${upgrades if upgrades else "pass"}


def downgrade():
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 8: 초기 마이그레이션 — `alembic/versions/0001_initial_users.py`**

```python
"""initial: users table

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("google_sub", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("sheet_url", sa.String(), nullable=True),
        sa.Column("smartlead_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(),
                  server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade():
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_table("users")
```

- [ ] **Step 9: 마이그레이션 동작 확인**

```bash
mkdir -p data
alembic upgrade head
python -c "from sqlalchemy import create_engine, inspect; e=create_engine('sqlite:///./data/app.db'); print(inspect(e).get_table_names())"
```

Expected: `['alembic_version', 'users']`.

- [ ] **Step 10: 다운그레이드도 동작하는지 확인**

```bash
alembic downgrade base
alembic upgrade head
```

Expected: 두 명령 모두 에러 없이 종료.

- [ ] **Step 11: 커밋**

```bash
git add app/models.py alembic.ini alembic/ tests/test_models.py
git commit -m "feat(db): User model + alembic initial migration"
```

---

## Task 5: 기존 server.py 라우트 → `app/crawl/router.py` 이관 (회귀 방지)

이 Task는 비즈니스 변경 없음. 단지 `server.py`에 모인 라우트를 모듈로 옮긴다. 기존 동작을 깨지 않는 것이 핵심.

**Files:**
- Create: `app/crawl/__init__.py` (빈)
- Create: `app/crawl/router.py`
- Create: `app/factory.py`
- Create: `tests/test_crawl_regression.py`
- Modify: `server.py`

- [ ] **Step 1: 회귀 테스트 작성 — `tests/test_crawl_regression.py`**

기존 라우트가 동일하게 응답하는지만 검증. 외부 의존성(크롤러 자체)은 mock.

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.factory import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_root_serves_index_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<!DOCTYPE html>" in r.text or "<html" in r.text


def test_static_mount_serves_files(client):
    r = client.get("/static/app.js")
    assert r.status_code == 200


def test_crawl_rejects_empty_keyword(client):
    r = client.post("/api/crawl", json={"keyword": "  ", "start_page": 1, "end_page": 2, "source": "saramin"})
    assert r.status_code == 400


def test_crawl_rejects_invalid_pages(client):
    r = client.post("/api/crawl", json={"keyword": "a", "start_page": 0, "end_page": 0, "source": "saramin"})
    assert r.status_code == 400


def test_crawl_rejects_unknown_source(client):
    r = client.post("/api/crawl", json={"keyword": "a", "start_page": 1, "end_page": 1, "source": "noexist"})
    assert r.status_code in (400, 500)  # 현재 코드는 500도 가능 — 양쪽 다 인정


def test_export_sheet_rejects_when_no_creds_env(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)
    r = client.post("/api/export/sheet", json={
        "sheet_url": "https://docs.google.com/spreadsheets/d/abc/edit",
        "companies": [],
        "keyword": "t", "source": "test",
    })
    assert r.status_code in (400, 500)


def test_google_sheet_config_endpoint(client):
    r = client.get("/api/config/google-sheet")
    assert r.status_code == 200
    assert "service_email" in r.json()
```

- [ ] **Step 2: 실패 확인 (모듈 부재)**

```bash
pytest tests/test_crawl_regression.py -v
```

Expected: ImportError on `app.factory.create_app`.

- [ ] **Step 3: `app/crawl/__init__.py` 빈 파일 생성**

- [ ] **Step 4: `app/crawl/router.py` 작성 — 기존 `server.py`의 라우트를 그대로 옮김**

원본의 모든 핸들러를 그대로 복사. `app = FastAPI(...)` 대신 `router = APIRouter()`. 함수 데코레이터는 `@router.get`/`@router.post`. CORS·StaticFiles·root 라우트는 factory에서 처리.

이관 대상 라우트:
- `POST /api/crawl`
- `POST /api/crawl/stream`
- `POST /api/export/sheet` (**중복 등록 1개만 옮기고 1개는 삭제** — 코드 리뷰 이슈)
- `GET /api/config/google-sheet`
- `GET /api/debug/jobkorea` (환경변수로 가드)

```python
"""
크롤링·시트 내보내기·디버그 라우트.
인증 없음 — 익명 사용자도 사용 가능.
"""
import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from crawlers import SaraminCrawler
from crawlers.jobkorea import JobKoreaCrawler
from crawlers.wanted import WantedCrawler
from utils.google_sheets import GoogleSheetExporter


router = APIRouter()


class CrawlRequest(BaseModel):
    keyword: str
    start_page: int = 1
    end_page: int = 5
    source: str = "saramin"


class ExportRequest(BaseModel):
    sheet_url: str
    companies: List[Dict[str, Any]]
    keyword: str = "검색어없음"
    source: str = "기타"


def _select_crawler(source: str):
    if source == "saramin":
        return SaraminCrawler
    if source == "jobkorea":
        return JobKoreaCrawler
    if source == "wanted":
        return WantedCrawler
    raise HTTPException(status_code=400, detail=f"지원하지 않는 소스: {source}")


@router.post("/api/crawl")
async def crawl(request: CrawlRequest):
    if not request.keyword.strip():
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")
    if request.start_page < 1 or request.end_page < 1:
        raise HTTPException(status_code=400, detail="페이지 번호는 1 이상이어야 합니다.")
    if request.start_page > request.end_page:
        raise HTTPException(status_code=400, detail="시작 페이지는 끝 페이지보다 작거나 같아야 합니다.")

    crawler_cls = _select_crawler(request.source)

    try:
        async with crawler_cls() as crawler:
            results = await crawler.crawl_with_emails(
                keyword=request.keyword,
                start_page=request.start_page,
                end_page=request.end_page,
            )
            return {
                "success": True,
                "keyword": request.keyword,
                "source": request.source,
                "total": len(results),
                "companies": results,
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/crawl/stream")
async def crawl_stream(request: CrawlRequest):
    if not request.keyword.strip():
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")
    if request.start_page < 1 or request.end_page < 1:
        raise HTTPException(status_code=400, detail="페이지 번호는 1 이상이어야 합니다.")
    if request.start_page > request.end_page:
        raise HTTPException(status_code=400, detail="시작 페이지는 끝 페이지보다 작거나 같아야 합니다.")

    async def generate():
        try:
            try:
                crawler_cls = _select_crawler(request.source)
            except HTTPException as he:
                yield f"data: {json.dumps({'type': 'error', 'message': he.detail})}\n\n"
                return

            async with crawler_cls() as crawler:
                companies = await crawler.search(request.keyword, request.start_page, request.end_page)
                total = len(companies)
                yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

                for idx, company in enumerate(companies):
                    try:
                        company["source"] = request.source

                        if request.source == "jobkorea" and company.get("job_url") and not company.get("company_url"):
                            company["company_url"] = await crawler._get_company_url_from_job(company["job_url"])

                        if company.get("company_url"):
                            detail = await crawler.get_company_detail(company["company_url"])
                            company["homepage"] = detail.get("homepage")

                        if company.get("homepage"):
                            company["emails"] = await crawler.email_extractor.extract_from_url(company["homepage"])

                        yield f"data: {json.dumps({'type': 'progress', 'current': idx + 1, 'total': total, 'company': company}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        company["error"] = str(e)
                        yield f"data: {json.dumps({'type': 'progress', 'current': idx + 1, 'total': total, 'company': company}, ensure_ascii=False)}\n\n"

                yield f"data: {json.dumps({'type': 'complete', 'total': total})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/api/export/sheet")
async def export_sheet(request: ExportRequest):
    try:
        exporter = GoogleSheetExporter()
        success, message = exporter.export_to_sheet(
            request.sheet_url, request.companies, request.keyword, request.source
        )
        if success:
            return {"success": True, "message": message}
        raise HTTPException(status_code=500, detail=message)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/config/google-sheet")
async def get_google_sheet_config():
    try:
        exporter = GoogleSheetExporter()
        email = exporter.get_service_email()
        return {"service_email": email}
    except Exception:
        return {"service_email": None}


@router.get("/api/debug/jobkorea")
async def debug_jobkorea(keyword: str = "개발자"):
    """Railway 환경 진단용. ENABLE_DEBUG_ROUTES=1 일 때만 응답."""
    if os.environ.get("ENABLE_DEBUG_ROUTES") != "1":
        raise HTTPException(status_code=404, detail="not found")

    results = {
        "keyword": keyword,
        "search_url": None,
        "search_response": {"status_code": None, "content_length": 0, "has_job_cards": False, "job_card_count": 0},
        "parsed_companies": [],
        "detail_test": {
            "job_url": None, "job_page_status": None, "job_page_length": 0,
            "co_read_pattern_found": False, "company_url": None,
            "company_page_status": None, "company_page_length": 0, "homepage_found": None,
        },
        "errors": [],
    }

    try:
        search_url = f"https://www.jobkorea.co.kr/Search/?stext={quote(keyword)}&Page_No=1"
        results["search_url"] = search_url
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
            response = await client.get(search_url)
            results["search_response"]["status_code"] = response.status_code
            results["search_response"]["content_length"] = len(response.text)
            soup = BeautifulSoup(response.text, "lxml")
            job_cards = soup.select('div[class*="Box_bgColor_white"][class*="Box_borderColor"]')
            results["search_response"]["has_job_cards"] = len(job_cards) > 0
            results["search_response"]["job_card_count"] = len(job_cards)

            async with JobKoreaCrawler() as crawler:
                companies = await crawler.search(keyword, 1, 1)
                results["parsed_companies"] = companies[:3]
                if companies and companies[0].get("job_url"):
                    job_url = companies[0]["job_url"]
                    results["detail_test"]["job_url"] = job_url
                    job_response = await client.get(job_url)
                    results["detail_test"]["job_page_status"] = job_response.status_code
                    results["detail_test"]["job_page_length"] = len(job_response.text)
                    match = re.search(r"/Recruit/Co_Read/C/(\d+)", job_response.text)
                    results["detail_test"]["co_read_pattern_found"] = match is not None
                    if match:
                        company_id = match.group(1)
                        company_url = f"https://www.jobkorea.co.kr/Recruit/Co_Read/C/{company_id}"
                        results["detail_test"]["company_url"] = company_url
                        company_response = await client.get(company_url)
                        results["detail_test"]["company_page_status"] = company_response.status_code
                        results["detail_test"]["company_page_length"] = len(company_response.text)
                        detail = await crawler.get_company_detail(company_url)
                        results["detail_test"]["homepage_found"] = detail.get("homepage")
    except Exception as e:
        results["errors"].append(str(e))

    return results
```

- [ ] **Step 5: `app/factory.py` 작성 — app factory + CORS + static + root**

```python
"""
FastAPI 앱 팩토리.
라우터 등록·미들웨어·정적 파일 마운트를 한 곳에서.
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def _cors_allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    # 기본: 로컬 개발 환경
    return ["http://localhost:8000", "http://127.0.0.1:8000"]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Email Crawler API",
        description="채용사이트 회사 이메일 크롤링 + Smartlead 자동화",
        version="2.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 라우터 (Plan 1 범위)
    from app.crawl.router import router as crawl_router
    app.include_router(crawl_router)

    # 루트 → 정적 index
    @app.get("/")
    async def root():
        return FileResponse("static/index.html")

    # 헬스 체크
    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    # 정적 파일
    app.mount("/static", StaticFiles(directory="static"), name="static")

    return app
```

- [ ] **Step 6: `server.py` 슬림화 — factory 호출만**

```python
"""
Email Crawler API Server — 엔트리포인트.
"""
from app.factory import create_app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

코드 리뷰 이슈도 함께 해결:
- 중복 `/api/export/sheet` 1개만 남김 (라우터 모듈로 이관 시 자연스럽게 해결).
- CORS `allow_origins=["*"]` + `allow_credentials=True` 모순 해결 (이제 명시적 origin 목록).
- 포트 8001 → 8000 정정.
- `/api/debug/jobkorea` 환경변수 가드 적용.

- [ ] **Step 7: 회귀 테스트 통과 확인**

```bash
pytest tests/test_crawl_regression.py -v
```

Expected: 7 passed.

- [ ] **Step 8: 수동 스모크 — 서버 띄우고 GET /, /static/style.css, /healthz, GET /api/config/google-sheet 확인**

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
sleep 2
curl -s http://localhost:8000/healthz
curl -sI http://localhost:8000/
curl -sI http://localhost:8000/static/style.css
curl -s http://localhost:8000/api/config/google-sheet
kill $SERVER_PID
```

Expected: `/healthz` → `{"status":"ok"}`, `/` 200, `/static/style.css` 200, `/api/config/google-sheet` → JSON.

- [ ] **Step 9: 커밋**

```bash
git add app/crawl/ app/factory.py server.py tests/test_crawl_regression.py
git commit -m "refactor: extract crawl routes to app/crawl, slim server.py, fix CORS+port+dup-route+debug-guard"
```

---

## Task 6: BaseCrawler 추상 메서드 시그니처 정합

코드 리뷰에서 발견한 이슈. 추상 시그니처와 구현 시그니처가 다름.

**Files:**
- Modify: `crawlers/base.py`

- [ ] **Step 1: `crawlers/base.py` 추상 메서드 시그니처 수정**

`search` 시그니처를 구현체와 일치시킴.

```python
# crawlers/base.py 의 search 부분만 교체

    @abstractmethod
    async def search(self, keyword: str, start_page: int = 1, end_page: int = 5) -> List[Dict[str, Any]]:
        """검색 수행 (하위 클래스에서 구현)"""
        pass
```

- [ ] **Step 2: 기존 크롤러 회귀 테스트 재실행**

```bash
pytest tests/test_crawl_regression.py -v
```

Expected: 여전히 통과.

- [ ] **Step 3: 커밋**

```bash
git add crawlers/base.py
git commit -m "fix(crawlers): align BaseCrawler.search signature with implementations"
```

---

## Task 7: OAuth 화이트리스트 검사

**Files:**
- Create: `app/auth/__init__.py` (빈)
- Create: `app/auth/whitelist.py`
- Create: `tests/test_whitelist.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/test_whitelist.py`**

```python
from app.auth.whitelist import is_email_allowed


def test_allowed_when_no_lists_configured():
    # 도메인·이메일 화이트리스트 둘 다 비어있으면 모두 허용 (개발용)
    assert is_email_allowed("anyone@anywhere.com", domains=[], emails=[]) is True


def test_allowed_when_domain_matches():
    assert is_email_allowed("alice@example.com", domains=["example.com"], emails=[]) is True
    assert is_email_allowed("bob@example.com", domains=["example.com", "other.com"], emails=[]) is True


def test_denied_when_domain_does_not_match():
    assert is_email_allowed("eve@bad.com", domains=["example.com"], emails=[]) is False


def test_allowed_when_email_matches_even_if_domain_denied():
    assert is_email_allowed(
        "consultant@external.com",
        domains=["example.com"],
        emails=["consultant@external.com"],
    ) is True


def test_email_match_case_insensitive():
    assert is_email_allowed("Alice@Example.COM", domains=[], emails=["alice@example.com"]) is True
    assert is_email_allowed("Alice@Example.COM", domains=["EXAMPLE.com"], emails=[]) is True


def test_or_match_when_both_lists_set():
    # 두 리스트 모두 설정 — 어느 한 쪽이라도 매칭하면 허용
    domains = ["example.com"]
    emails = ["consultant@external.com"]
    assert is_email_allowed("alice@example.com", domains=domains, emails=emails) is True
    assert is_email_allowed("consultant@external.com", domains=domains, emails=emails) is True
    assert is_email_allowed("eve@bad.com", domains=domains, emails=emails) is False
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_whitelist.py -v
```

Expected: ImportError.

- [ ] **Step 3: 모듈 작성 — `app/auth/__init__.py` 빈 파일**

- [ ] **Step 4: `app/auth/whitelist.py` 구현**

```python
"""
OAuth 화이트리스트 검사.
도메인·이메일 둘 다 설정된 경우 OR 매칭 — 어느 한쪽이라도 통과하면 허용.
둘 다 비어있으면 모든 Google 계정 허용(개발용).
"""
from typing import List


def is_email_allowed(email: str, domains: List[str], emails: List[str]) -> bool:
    if not domains and not emails:
        return True

    email_l = email.lower().strip()
    domains_l = [d.lower().strip() for d in domains if d.strip()]
    emails_l = [e.lower().strip() for e in emails if e.strip()]

    domain_part = email_l.split("@")[-1] if "@" in email_l else ""

    if domains_l and domain_part in domains_l:
        return True
    if emails_l and email_l in emails_l:
        return True
    return False
```

- [ ] **Step 5: 통과 확인**

```bash
pytest tests/test_whitelist.py -v
```

Expected: 6 passed.

- [ ] **Step 6: 커밋**

```bash
git add app/auth/__init__.py app/auth/whitelist.py tests/test_whitelist.py
git commit -m "feat(auth): email/domain whitelist matcher"
```

---

## Task 8: 세션 쿠키 모듈

**Files:**
- Create: `app/auth/session.py`
- Create: `tests/test_session.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/test_session.py`**

```python
from fastapi import FastAPI, Response, Request, Depends
from fastapi.testclient import TestClient

from app.auth.session import (
    set_session_cookie, read_session, clear_session_cookie,
    SESSION_COOKIE_NAME,
)


def make_app():
    app = FastAPI()

    @app.post("/login")
    def login(response: Response):
        set_session_cookie(response, user_id=42)
        return {"ok": True}

    @app.get("/whoami")
    def whoami(request: Request):
        return {"user_id": read_session(request)}

    @app.post("/logout")
    def logout(response: Response):
        clear_session_cookie(response)
        return {"ok": True}

    return app


def test_set_and_read_session():
    client = TestClient(make_app())
    r = client.post("/login")
    assert r.status_code == 200
    assert SESSION_COOKIE_NAME in r.cookies
    r2 = client.get("/whoami")
    assert r2.json() == {"user_id": 42}


def test_unsigned_cookie_rejected():
    client = TestClient(make_app())
    client.cookies.set(SESSION_COOKIE_NAME, "garbage")
    r = client.get("/whoami")
    assert r.json() == {"user_id": None}


def test_logout_clears_session():
    client = TestClient(make_app())
    client.post("/login")
    client.post("/logout")
    r = client.get("/whoami")
    assert r.json() == {"user_id": None}
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_session.py -v
```

Expected: ImportError.

- [ ] **Step 3: `app/auth/session.py` 구현**

```python
"""
세션 쿠키. itsdangerous로 user_id 서명·검증.
HttpOnly + SameSite=Lax + 30일 만료.
"""
from typing import Optional

from fastapi import Request, Response
from itsdangerous import BadSignature, TimestampSigner

from app.config import get_settings


SESSION_COOKIE_NAME = "emailmak_session"
MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 30일


def _signer() -> TimestampSigner:
    return TimestampSigner(get_settings().app_secret_key, salt="session-v1")


def set_session_cookie(response: Response, user_id: int) -> None:
    token = _signer().sign(str(user_id)).decode("utf-8")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,  # 프로덕션 HTTPS 환경에선 True로 (리버스 프록시가 처리)
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)


def read_session(request: Request) -> Optional[int]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        raw = _signer().unsign(token, max_age=MAX_AGE_SECONDS).decode("utf-8")
        return int(raw)
    except (BadSignature, ValueError):
        return None
```

- [ ] **Step 4: 통과 확인**

```bash
pytest tests/test_session.py -v
```

Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add app/auth/session.py tests/test_session.py
git commit -m "feat(auth): signed session cookie helpers"
```

---

## Task 9: `require_login` / `get_current_user` 의존성

**Files:**
- Create: `app/auth/deps.py`
- Create: `tests/test_auth_deps.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/test_auth_deps.py`**

```python
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from app.db import Base, engine, SessionLocal
from app.models import User
from app.auth.session import set_session_cookie
from app.auth.deps import require_login, get_current_user


@pytest.fixture(autouse=True)
def db_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def make_app():
    app = FastAPI()

    @app.post("/_test_login/{uid}")
    def _test_login(uid: int):
        from fastapi.responses import JSONResponse
        resp = JSONResponse({"ok": True})
        set_session_cookie(resp, user_id=uid)
        return resp

    @app.get("/me")
    def me(user: User = Depends(require_login)):
        return {"email": user.email, "id": user.id}

    @app.get("/maybe-me")
    def maybe_me(user: User | None = Depends(get_current_user)):
        return {"user": user.email if user else None}

    return app


def _seed_user(email="alice@example.com", sub="g-1"):
    s = SessionLocal()
    try:
        u = User(google_sub=sub, email=email, name="A")
        s.add(u); s.commit(); s.refresh(u)
        return u.id
    finally:
        s.close()


def test_require_login_returns_401_when_no_cookie():
    client = TestClient(make_app())
    r = client.get("/me")
    assert r.status_code == 401


def test_require_login_returns_401_when_user_missing():
    client = TestClient(make_app())
    client.post("/_test_login/999")  # 존재하지 않는 user_id
    r = client.get("/me")
    assert r.status_code == 401


def test_require_login_returns_user_when_authenticated():
    uid = _seed_user()
    client = TestClient(make_app())
    client.post(f"/_test_login/{uid}")
    r = client.get("/me")
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.com"


def test_get_current_user_returns_none_when_anonymous():
    client = TestClient(make_app())
    r = client.get("/maybe-me")
    assert r.status_code == 200
    assert r.json() == {"user": None}


def test_get_current_user_returns_user_when_logged_in():
    uid = _seed_user(email="bob@example.com", sub="g-2")
    client = TestClient(make_app())
    client.post(f"/_test_login/{uid}")
    r = client.get("/maybe-me")
    assert r.json() == {"user": "bob@example.com"}
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_auth_deps.py -v
```

Expected: ImportError on `app.auth.deps`.

- [ ] **Step 3: `app/auth/deps.py` 구현**

```python
"""
FastAPI 의존성: 로그인 검사 / 현재 사용자 조회.
"""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.auth.session import read_session


def get_current_user(
    request: Request,
    db: Session = Depends(get_session),
) -> Optional[User]:
    """세션이 있고 유효한 user면 반환, 아니면 None."""
    user_id = read_session(request)
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_login(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """없으면 401."""
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    return user
```

- [ ] **Step 4: 통과 확인**

```bash
pytest tests/test_auth_deps.py -v
```

Expected: 5 passed.

- [ ] **Step 5: 커밋**

```bash
git add app/auth/deps.py tests/test_auth_deps.py
git commit -m "feat(auth): require_login + get_current_user FastAPI deps"
```

---

## Task 10: Google OAuth 클라이언트 (authlib 래퍼)

**Files:**
- Create: `app/auth/oauth.py`
- Create: `tests/test_oauth_client.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/test_oauth_client.py`**

OAuth 자체는 외부 통신이라 단위 테스트는 URL 빌드와 ID 토큰 파싱에 한정. 실제 callback은 Task 11 통합 테스트에서.

```python
from app.auth.oauth import build_authorization_url, parse_userinfo


def test_authorization_url_contains_required_params():
    url = build_authorization_url(redirect_uri="http://localhost:8000/api/auth/callback", state="s-abc")
    assert "accounts.google.com/o/oauth2/v2/auth" in url
    assert "client_id=test-client-id" in url
    assert "response_type=code" in url
    assert "scope=openid+email+profile" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fauth%2Fcallback" in url
    assert "state=s-abc" in url


def test_parse_userinfo_extracts_sub_email_name():
    payload = {"sub": "10001", "email": "alice@example.com", "name": "Alice",
               "email_verified": True}
    info = parse_userinfo(payload)
    assert info.sub == "10001"
    assert info.email == "alice@example.com"
    assert info.name == "Alice"


def test_parse_userinfo_rejects_unverified_email():
    import pytest
    payload = {"sub": "x", "email": "x@y.com", "email_verified": False}
    with pytest.raises(ValueError):
        parse_userinfo(payload)
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_oauth_client.py -v
```

Expected: ImportError.

- [ ] **Step 3: `app/auth/oauth.py` 구현**

```python
"""
Google OAuth2 클라이언트.
authlib을 직접 쓰지 않고, 명시적 토큰 교환만 수행 (테스트 용이성).
"""
from dataclasses import dataclass
from typing import Any, Dict
from urllib.parse import urlencode

import httpx

from app.config import get_settings


AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass
class UserInfo:
    sub: str
    email: str
    name: str


def build_authorization_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": get_settings().google_oauth_client_id,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": redirect_uri,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_userinfo(code: str, redirect_uri: str) -> UserInfo:
    s = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(TOKEN_URL, data={
            "code": code,
            "client_id": s.google_oauth_client_id,
            "client_secret": s.google_oauth_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        info_resp = await client.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        info_resp.raise_for_status()
        return parse_userinfo(info_resp.json())


def parse_userinfo(payload: Dict[str, Any]) -> UserInfo:
    if not payload.get("email_verified", False):
        raise ValueError("email not verified by Google")
    return UserInfo(
        sub=str(payload["sub"]),
        email=str(payload["email"]).lower().strip(),
        name=str(payload.get("name") or ""),
    )
```

- [ ] **Step 4: 통과 확인**

```bash
pytest tests/test_oauth_client.py -v
```

Expected: 3 passed.

- [ ] **Step 5: 커밋**

```bash
git add app/auth/oauth.py tests/test_oauth_client.py
git commit -m "feat(auth): Google OAuth URL builder + userinfo parser"
```

---

## Task 11: OAuth 라우터 (`/api/auth/start`, `/callback`, `/logout`) + User upsert

**Files:**
- Create: `app/users/__init__.py` (빈)
- Create: `app/users/service.py`
- Create: `app/auth/router.py`
- Modify: `app/factory.py` (라우터 등록)
- Create: `tests/test_auth_flow.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/test_auth_flow.py`**

`exchange_code_for_userinfo`를 mock으로 대체. 실제 Google 통신은 안 함.

```python
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.db import Base, engine, SessionLocal
from app.models import User
from app.factory import create_app
from app.auth.oauth import UserInfo


@pytest.fixture(autouse=True)
def db_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(create_app())


def test_auth_start_redirects_to_google(client):
    r = client.get("/api/auth/start", follow_redirects=False)
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    assert loc.startswith("https://accounts.google.com/")
    # state 쿠키도 세팅되어야 함
    assert "oauth_state" in r.cookies


def test_auth_callback_creates_user_and_sets_session(client):
    # 1) /start로 state 발급
    r1 = client.get("/api/auth/start", follow_redirects=False)
    state = r1.cookies["oauth_state"]

    # 2) /callback에 같은 state로 진입
    fake_info = UserInfo(sub="g-123", email="alice@example.com", name="Alice")
    with patch("app.auth.router.exchange_code_for_userinfo",
               new=AsyncMock(return_value=fake_info)):
        r2 = client.get(
            "/api/auth/callback",
            params={"code": "fake-code", "state": state},
            follow_redirects=False,
        )

    assert r2.status_code in (302, 307)
    # DB에 사용자가 생겼는지
    s = SessionLocal()
    try:
        u = s.query(User).filter(User.email == "alice@example.com").first()
        assert u is not None
        assert u.google_sub == "g-123"
    finally:
        s.close()
    # 세션 쿠키가 설정되었는지
    assert "emailmak_session" in r2.cookies


def test_auth_callback_rejects_mismatched_state(client):
    client.get("/api/auth/start", follow_redirects=False)
    r = client.get(
        "/api/auth/callback",
        params={"code": "any", "state": "totally-different-state"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_auth_callback_rejects_disallowed_email(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_OAUTH_DOMAIN", "permitted.com")
    # config는 lru_cache라 리로드 필요
    from importlib import reload
    from app import config as cm
    reload(cm)

    r1 = client.get("/api/auth/start", follow_redirects=False)
    state = r1.cookies["oauth_state"]

    fake = UserInfo(sub="g-x", email="outsider@bad.com", name="X")
    with patch("app.auth.router.exchange_code_for_userinfo",
               new=AsyncMock(return_value=fake)):
        r2 = client.get(
            "/api/auth/callback",
            params={"code": "c", "state": state},
            follow_redirects=False,
        )
    assert r2.status_code == 403


def test_auth_logout_clears_session(client):
    # 가짜 로그인
    r1 = client.get("/api/auth/start", follow_redirects=False)
    state = r1.cookies["oauth_state"]
    fake = UserInfo(sub="g-1", email="alice@example.com", name="A")
    with patch("app.auth.router.exchange_code_for_userinfo",
               new=AsyncMock(return_value=fake)):
        client.get("/api/auth/callback",
                   params={"code": "c", "state": state},
                   follow_redirects=False)

    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    # 세션 쿠키 삭제 응답 헤더
    assert "emailmak_session" in r.headers.get("set-cookie", "")
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_auth_flow.py -v
```

Expected: ImportError.

- [ ] **Step 3: `app/users/__init__.py` 빈 파일 생성**

- [ ] **Step 4: `app/users/service.py` 구현 — User upsert**

```python
"""
사용자 도메인 로직.
Plan 1 범위: OAuth로 받은 UserInfo로 upsert + 온보딩 저장.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import User
from app.auth.oauth import UserInfo
from app.crypto import encrypt_secret


def upsert_from_oauth(db: Session, info: UserInfo) -> User:
    """google_sub 기준으로 유저 upsert. 이메일·이름은 매 로그인마다 갱신."""
    user = db.query(User).filter(User.google_sub == info.sub).first()
    if user is None:
        # 이메일이 이미 다른 sub로 등록된 경우 — Google 계정 변경 케이스, sub 갱신
        existing_by_email = db.query(User).filter(User.email == info.email).first()
        if existing_by_email is not None:
            existing_by_email.google_sub = info.sub
            existing_by_email.name = info.name
            existing_by_email.last_login_at = datetime.utcnow()
            db.commit()
            db.refresh(existing_by_email)
            return existing_by_email

        user = User(google_sub=info.sub, email=info.email, name=info.name,
                    last_login_at=datetime.utcnow())
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    user.email = info.email
    user.name = info.name
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def save_onboarding(db: Session, user: User, sheet_url: Optional[str],
                    smartlead_key_plain: Optional[str]) -> User:
    """온보딩 화면에서 받은 값 저장. None이면 기존 값 보존."""
    if sheet_url is not None:
        user.sheet_url = sheet_url.strip() or None
    if smartlead_key_plain is not None:
        sk = smartlead_key_plain.strip()
        user.smartlead_key = encrypt_secret(sk) if sk else None
    db.commit()
    db.refresh(user)
    return user
```

- [ ] **Step 5: `app/auth/router.py` 구현**

```python
"""
OAuth 라우트.
/api/auth/start   → Google 동의 화면으로 리다이렉트, state 쿠키 발급
/api/auth/callback → code 교환, 화이트리스트 검사, upsert, 세션 발급
/api/auth/logout  → 세션 쿠키 삭제
"""
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.auth.oauth import build_authorization_url, exchange_code_for_userinfo
from app.auth.session import set_session_cookie, clear_session_cookie
from app.auth.whitelist import is_email_allowed
from app.users.service import upsert_from_oauth


router = APIRouter(prefix="/api/auth")

STATE_COOKIE = "oauth_state"
STATE_MAX_AGE = 600  # 10분


def _build_redirect_uri(request: Request) -> str:
    # Railway 등 프록시 뒤에서도 동작하도록 X-Forwarded-Proto 우선
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{proto}://{host}/api/auth/callback"


@router.get("/start")
async def auth_start(request: Request):
    state = secrets.token_urlsafe(32)
    redirect_uri = _build_redirect_uri(request)
    auth_url = build_authorization_url(redirect_uri=redirect_uri, state=state)
    resp = RedirectResponse(url=auth_url, status_code=302)
    resp.set_cookie(STATE_COOKIE, state, max_age=STATE_MAX_AGE,
                    httponly=True, samesite="lax", secure=False)
    return resp


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_session),
):
    if error:
        return RedirectResponse(url=f"/?auth_error={error}", status_code=302)
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code/state")

    cookie_state = request.cookies.get(STATE_COOKIE)
    if not cookie_state or cookie_state != state:
        raise HTTPException(status_code=400, detail="state mismatch")

    redirect_uri = _build_redirect_uri(request)
    info = await exchange_code_for_userinfo(code=code, redirect_uri=redirect_uri)

    s = get_settings()
    if not is_email_allowed(info.email, s.allowed_oauth_domains, s.allowed_oauth_emails_list):
        raise HTTPException(status_code=403, detail="이 계정은 사용이 허용되지 않았습니다.")

    user = upsert_from_oauth(db, info)
    # 온보딩 완료 여부에 따라 분기
    next_path = "/" if (user.sheet_url and user.smartlead_key) else "/static/onboarding.html"
    resp = RedirectResponse(url=next_path, status_code=302)
    set_session_cookie(resp, user_id=user.id)
    resp.delete_cookie(STATE_COOKIE)
    return resp


@router.post("/logout")
async def auth_logout():
    resp = JSONResponse({"ok": True})
    clear_session_cookie(resp)
    return resp
```

- [ ] **Step 6: `app/factory.py` 에 auth 라우터 등록**

`app/factory.py`의 `# 라우터 (Plan 1 범위)` 블록을 다음으로 교체:

```python
    # 라우터 (Plan 1 범위)
    from app.crawl.router import router as crawl_router
    from app.auth.router import router as auth_router
    app.include_router(crawl_router)
    app.include_router(auth_router)
```

- [ ] **Step 7: 통과 확인**

```bash
pytest tests/test_auth_flow.py -v
```

Expected: 5 passed.

- [ ] **Step 8: 커밋**

```bash
git add app/users/ app/auth/router.py app/factory.py tests/test_auth_flow.py
git commit -m "feat(auth): OAuth start/callback/logout + user upsert"
```

---

## Task 12: `/api/users/me` + `/api/users/onboard` 라우터

**Files:**
- Create: `app/users/schemas.py`
- Create: `app/users/router.py`
- Modify: `app/factory.py` (users 라우터 등록)
- Create: `tests/test_users_router.py`

- [ ] **Step 1: 실패 테스트 작성 — `tests/test_users_router.py`**

```python
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.db import Base, engine, SessionLocal
from app.models import User
from app.factory import create_app
from app.auth.oauth import UserInfo
from app.crypto import decrypt_secret


@pytest.fixture(autouse=True)
def db_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(create_app())


def _login(client, email="alice@example.com", sub="g-1"):
    r1 = client.get("/api/auth/start", follow_redirects=False)
    state = r1.cookies["oauth_state"]
    fake = UserInfo(sub=sub, email=email, name="A")
    with patch("app.auth.router.exchange_code_for_userinfo",
               new=AsyncMock(return_value=fake)):
        client.get("/api/auth/callback",
                   params={"code": "c", "state": state},
                   follow_redirects=False)


def test_me_requires_login(client):
    r = client.get("/api/users/me")
    assert r.status_code == 401


def test_me_returns_user_info_when_logged_in(client):
    _login(client)
    r = client.get("/api/users/me")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "alice@example.com"
    assert data["sheet_url"] is None
    assert data["has_smartlead_key"] is False


def test_onboard_saves_sheet_and_key(client):
    _login(client)
    r = client.post("/api/users/onboard", json={
        "sheet_url": "https://docs.google.com/spreadsheets/d/abc/edit",
        "smartlead_key": "sk-real-smartlead-token-1234567890",
    })
    assert r.status_code == 200
    # me에 반영되는지
    me = client.get("/api/users/me").json()
    assert me["sheet_url"].startswith("https://docs.google.com")
    assert me["has_smartlead_key"] is True
    assert "sk-r***7890" in me["smartlead_key_masked"]
    # DB 저장값은 암호화되어 있어야 함
    s = SessionLocal()
    try:
        u = s.query(User).first()
        assert u.smartlead_key != "sk-real-smartlead-token-1234567890"
        assert decrypt_secret(u.smartlead_key) == "sk-real-smartlead-token-1234567890"
    finally:
        s.close()


def test_onboard_requires_login(client):
    r = client.post("/api/users/onboard", json={"sheet_url": "x", "smartlead_key": "y"})
    assert r.status_code == 401


def test_onboard_partial_update_preserves_existing(client):
    _login(client)
    client.post("/api/users/onboard", json={
        "sheet_url": "https://docs.google.com/spreadsheets/d/v1/edit",
        "smartlead_key": "sk-key-first-12345678",
    })
    # 이번엔 sheet_url만 갱신
    r = client.post("/api/users/onboard", json={
        "sheet_url": "https://docs.google.com/spreadsheets/d/v2/edit",
    })
    assert r.status_code == 200
    me = client.get("/api/users/me").json()
    assert "v2" in me["sheet_url"]
    assert me["has_smartlead_key"] is True  # 기존 키 유지


def test_onboard_validates_sheet_url(client):
    _login(client)
    r = client.post("/api/users/onboard", json={
        "sheet_url": "not-a-url",
        "smartlead_key": "sk-anything",
    })
    assert r.status_code == 422 or r.status_code == 400
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_users_router.py -v
```

Expected: ImportError.

- [ ] **Step 3: `app/users/schemas.py` 구현**

```python
"""
Users 요청·응답 스키마.
"""
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class OnboardRequest(BaseModel):
    sheet_url: Optional[str] = None
    smartlead_key: Optional[str] = Field(default=None, min_length=8, max_length=512)

    @field_validator("sheet_url")
    @classmethod
    def _validate_sheet_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        if not (v.startswith("https://docs.google.com/") or v.startswith("https://sheets.google.com/")):
            raise ValueError("Google Sheets URL이어야 합니다")
        return v


class MeResponse(BaseModel):
    id: int
    email: str
    name: Optional[str]
    sheet_url: Optional[str]
    has_smartlead_key: bool
    smartlead_key_masked: Optional[str]
```

- [ ] **Step 4: `app/users/router.py` 구현**

```python
"""
사용자 정보·온보딩 라우트. 로그인 필수.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.auth.deps import require_login
from app.crypto import decrypt_secret, mask_secret
from app.users.schemas import OnboardRequest, MeResponse
from app.users.service import save_onboarding


router = APIRouter(prefix="/api/users")


def _to_me_response(user: User) -> MeResponse:
    masked: str | None = None
    if user.smartlead_key:
        try:
            masked = mask_secret(decrypt_secret(user.smartlead_key))
        except Exception:
            masked = "***"
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        sheet_url=user.sheet_url,
        has_smartlead_key=bool(user.smartlead_key),
        smartlead_key_masked=masked,
    )


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(require_login)):
    return _to_me_response(user)


@router.post("/onboard", response_model=MeResponse)
async def onboard(
    payload: OnboardRequest,
    user: User = Depends(require_login),
    db: Session = Depends(get_session),
):
    user = save_onboarding(db, user, payload.sheet_url, payload.smartlead_key)
    return _to_me_response(user)
```

- [ ] **Step 5: `app/factory.py` 에 users 라우터 등록**

```python
    # 라우터 (Plan 1 범위)
    from app.crawl.router import router as crawl_router
    from app.auth.router import router as auth_router
    from app.users.router import router as users_router
    app.include_router(crawl_router)
    app.include_router(auth_router)
    app.include_router(users_router)
```

- [ ] **Step 6: 통과 확인**

```bash
pytest tests/test_users_router.py -v
```

Expected: 6 passed.

- [ ] **Step 7: 커밋**

```bash
git add app/users/schemas.py app/users/router.py app/factory.py tests/test_users_router.py
git commit -m "feat(users): /api/users/me + /api/users/onboard with masked secret"
```

---

## Task 13: 프론트엔드 — 헤더 "시작하기" 버튼 + 로그인 상태 표시

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/style.css`

- [ ] **Step 1: `static/index.html` 헤더에 인증 영역 추가**

기존 `<header class="header">` 블록을 다음으로 교체:

```html
        <header class="header">
            <div class="logo">
                <span class="logo-icon">📧</span>
                <h1>Email Crawler</h1>
            </div>
            <p class="subtitle">채용사이트에서 회사 이메일을 자동으로 수집합니다</p>

            <div id="authBar" class="auth-bar">
                <button id="signInBtn" class="btn-secondary hidden" type="button">Google로 시작하기</button>
                <div id="userBadge" class="user-badge hidden">
                    <span id="userEmail"></span>
                    <a id="onboardingLink" class="link-btn" href="/static/onboarding.html">설정</a>
                    <button id="signOutBtn" class="btn-secondary" type="button">로그아웃</button>
                </div>
            </div>
        </header>
```

- [ ] **Step 2: `static/style.css` 에 인증 바 스타일 추가**

파일 끝에 추가:

```css
.auth-bar { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
.user-badge { display: flex; gap: 10px; align-items: center; font-size: 0.9rem; }
.user-badge span { opacity: 0.85; }
.hidden { display: none !important; }
```

- [ ] **Step 3: `static/app.js` 상단에 인증 초기화 추가**

기존 `// Initialize` 블록 위에 다음 함수와 호출을 추가. 기존 `DOMContentLoaded` 핸들러에서 호출:

```javascript
async function initAuth() {
    const signInBtn = document.getElementById('signInBtn');
    const signOutBtn = document.getElementById('signOutBtn');
    const userBadge = document.getElementById('userBadge');
    const userEmail = document.getElementById('userEmail');

    try {
        const res = await fetch('/api/users/me', { credentials: 'include' });
        if (res.status === 200) {
            const me = await res.json();
            userEmail.textContent = me.email;
            userBadge.classList.remove('hidden');
            signInBtn.classList.add('hidden');
            // 온보딩이 안 끝났으면 자동 안내
            if (!me.sheet_url || !me.has_smartlead_key) {
                showToast('설정이 완료되지 않았습니다. 우측 상단 "설정"을 눌러 완료해주세요.', 'warning');
            }
        } else {
            signInBtn.classList.remove('hidden');
            userBadge.classList.add('hidden');
        }
    } catch (e) {
        signInBtn.classList.remove('hidden');
    }

    signInBtn.addEventListener('click', () => {
        window.location.href = '/api/auth/start';
    });
    signOutBtn.addEventListener('click', async () => {
        await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
        window.location.reload();
    });
}
```

기존 `document.addEventListener('DOMContentLoaded', () => { initEventListeners(); });` 를 다음으로 교체:

```javascript
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    initAuth();
});
```

- [ ] **Step 4: 수동 스모크**

```bash
uvicorn server:app --port 8000 &
SERVER_PID=$!
sleep 2
curl -sI http://localhost:8000/ | head -1
curl -s http://localhost:8000/static/app.js | grep "initAuth" | head -1
kill $SERVER_PID
```

Expected: `200 OK`, `initAuth` 함수 라인이 출력됨.

- [ ] **Step 5: 커밋**

```bash
git add static/index.html static/app.js static/style.css
git commit -m "feat(ui): auth bar with sign-in/sign-out and onboarding prompt"
```

---

## Task 14: 온보딩 화면 (`/static/onboarding.html` + `onboarding.js`)

**Files:**
- Create: `static/onboarding.html`
- Create: `static/onboarding.js`

- [ ] **Step 1: `static/onboarding.html` 작성**

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>설정 — Email Crawler</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo"><span class="logo-icon">⚙️</span><h1>설정</h1></div>
            <p class="subtitle">한 번만 설정하면 됩니다. 언제든지 다시 와서 수정할 수 있어요.</p>
            <a href="/" class="link-btn">← 메인으로</a>
        </header>

        <section class="search-section">
            <div class="search-card">
                <div class="input-group">
                    <label>로그인된 계정</label>
                    <input id="meEmail" type="text" readonly disabled value="로딩중...">
                </div>

                <div class="input-group">
                    <label for="sheetUrl">개인 Google Sheet URL</label>
                    <input id="sheetUrl" type="text" placeholder="https://docs.google.com/spreadsheets/d/..." autocomplete="off">
                    <p class="modal-desc">
                        ① 본인 명의의 Google Sheets 문서를 만들고 ② 봇 이메일 <code id="botEmail">로딩중...</code> 을 <b>편집자</b>로 초대한 뒤 ③ 시트 URL을 붙여넣으세요.
                    </p>
                </div>

                <div class="input-group">
                    <label for="smartleadKey">Smartlead API 키</label>
                    <input id="smartleadKey" type="password" placeholder="sk-...">
                    <p class="modal-desc">현재 저장 상태: <code id="smartleadStatus">로딩중...</code></p>
                </div>

                <div class="button-group">
                    <button id="saveBtn" type="button" class="btn-primary">저장</button>
                </div>
            </div>
        </section>
    </div>

    <script src="/static/onboarding.js"></script>
</body>
</html>
```

- [ ] **Step 2: `static/onboarding.js` 작성**

```javascript
const meEmail = document.getElementById('meEmail');
const sheetUrlInput = document.getElementById('sheetUrl');
const smartleadKeyInput = document.getElementById('smartleadKey');
const smartleadStatus = document.getElementById('smartleadStatus');
const botEmail = document.getElementById('botEmail');
const saveBtn = document.getElementById('saveBtn');

function toast(msg, type = 'info') {
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = `position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
        padding:12px 24px;border-radius:8px;font-weight:500;color:white;
        background:${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#6366f1'};
        z-index:1000;`;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2500);
}

async function loadMe() {
    const res = await fetch('/api/users/me', { credentials: 'include' });
    if (res.status === 401) {
        window.location.href = '/api/auth/start';
        return;
    }
    const me = await res.json();
    meEmail.value = me.email;
    sheetUrlInput.value = me.sheet_url || '';
    smartleadStatus.textContent = me.has_smartlead_key
        ? `저장됨 (${me.smartlead_key_masked || '***'})`
        : '미설정';
}

async function loadBotEmail() {
    try {
        const res = await fetch('/api/config/google-sheet');
        const data = await res.json();
        botEmail.textContent = data.service_email || '미설정 (서버 환경변수 확인)';
    } catch (e) {
        botEmail.textContent = '로드 실패';
    }
}

async function save() {
    const payload = {};
    const url = sheetUrlInput.value.trim();
    const key = smartleadKeyInput.value.trim();
    if (url) payload.sheet_url = url;
    if (key) payload.smartlead_key = key;

    if (Object.keys(payload).length === 0) {
        toast('변경할 값을 입력하세요', 'error');
        return;
    }

    saveBtn.disabled = true;
    try {
        const res = await fetch('/api/users/onboard', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            toast(err.detail || `저장 실패 (${res.status})`, 'error');
            return;
        }
        smartleadKeyInput.value = '';
        toast('저장되었습니다', 'success');
        await loadMe();
    } finally {
        saveBtn.disabled = false;
    }
}

saveBtn.addEventListener('click', save);
loadMe();
loadBotEmail();
```

- [ ] **Step 3: 수동 스모크 — 페이지 로드 확인**

```bash
uvicorn server:app --port 8000 &
SERVER_PID=$!
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/static/onboarding.html
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/static/onboarding.js
kill $SERVER_PID
```

Expected: 두 응답 모두 `200`.

- [ ] **Step 4: 커밋**

```bash
git add static/onboarding.html static/onboarding.js
git commit -m "feat(ui): onboarding page for sheet URL + smartlead key"
```

---

## Task 15: Procfile/Railway 진입점 정정 + Plan 1 통합 점검

**Files:**
- Modify: `Procfile`
- Modify: `railway.json`
- Modify: `README.md`

- [ ] **Step 1: `Procfile` — 포트 변수 그대로 유지하되 모듈 동일 (server:app 그대로)**

기존 Procfile은 이미 `web: uvicorn server:app --host 0.0.0.0 --port $PORT` 라서 변경 없음. 확인만:

```bash
cat Procfile
```

Expected: `web: uvicorn server:app --host 0.0.0.0 --port $PORT`

- [ ] **Step 2: `railway.json` 확인 (기존 그대로)**

```bash
cat railway.json
```

Expected: `startCommand`가 `uvicorn server:app --host 0.0.0.0 --port $PORT`.

- [ ] **Step 3: `README.md` 의 포트 표기 정정 (8000으로 통일)**

`README.md`에서 다음 부분을 확인하고 8000이 맞는지 점검:

```
### 3. 접속

브라우저에서 `http://localhost:8000` 접속
```

이미 8000으로 표기되어 있을 것 — 변경 불필요. (변경 필요한 곳이 있으면 8000으로 통일.)

추가로 README에 환경변수 섹션을 보강:

`## 📊 구글 시트 연동 설정` 섹션 바로 위에 다음 섹션을 삽입:

```markdown
## 🔐 환경 변수 (Plan 1 기준)

| 이름 | 필수 | 설명 |
|------|------|------|
| `APP_SECRET_KEY` | ✅ | 세션 서명·시크릿 암호화에 쓰는 32바이트 이상 문자열. 한번 정하면 변경 금지 (변경 시 모든 세션·저장된 키 무효화). |
| `GOOGLE_OAUTH_CLIENT_ID` | ✅ | Google Cloud에서 발급한 OAuth 클라이언트 ID. |
| `GOOGLE_OAUTH_CLIENT_SECRET` | ✅ | OAuth 클라이언트 시크릿. |
| `DATABASE_URL` | 선택 | 기본값 `sqlite:///./data/app.db`. Railway 볼륨 `/data`에 매핑되면 `sqlite:////data/app.db`로 설정. |
| `ALLOWED_OAUTH_DOMAIN` | 선택 | 콤마구분 도메인 화이트리스트 (예: `mycompany.com,partner.com`). |
| `ALLOWED_OAUTH_EMAILS` | 선택 | 콤마구분 이메일 화이트리스트. |
| `ALLOWED_ORIGINS` | 선택 | CORS 허용 origin (콤마구분). 기본값은 localhost. |
| `GOOGLE_CREDENTIALS_JSON` | ✅ (시트 사용 시) | 기존 서비스 계정 JSON. |
| `ENABLE_DEBUG_ROUTES` | 선택 | `1`이면 `/api/debug/jobkorea` 활성화. 프로덕션에선 비워 둘 것. |

Google OAuth 발급 시 승인된 리디렉션 URI: `https://<your-domain>/api/auth/callback`.
```

- [ ] **Step 4: 전체 테스트 한 번 실행**

```bash
pytest -v
```

Expected: 모든 테스트 통과.

- [ ] **Step 5: 수동 E2E (mock 없이 끝까지) — 로컬에서 OAuth 작동 점검**

> 이 단계는 **개발자가 실제로 Google Cloud에서 OAuth 클라이언트를 만든 뒤에만 가능**합니다. 자동화하지 않습니다. 다음을 손으로 확인:

1. `.env` 파일에 `APP_SECRET_KEY`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` 채움.
2. `alembic upgrade head` 실행하여 `data/app.db` 생성.
3. `uvicorn server:app --reload --port 8000` 실행.
4. 브라우저로 `http://localhost:8000` 접속 → "Google로 시작하기" → 동의 → 콜백 → 온보딩 페이지 자동 이동(미설정인 경우).
5. 온보딩에서 시트 URL + Smartlead 키 입력 → 저장.
6. 메인으로 돌아가 우상단에 본인 이메일 + "설정"/"로그아웃" 배지 표시 확인.
7. 익명 모드(시크릿 창)에서 메인 접속하여 크롤링 가능한지 확인 (회귀 검사).

- [ ] **Step 6: 커밋**

```bash
git add README.md
git commit -m "docs: env var reference + OAuth redirect URI"
```

---

## Self-Review 결과

스펙 대비 Plan 1 범위 커버리지 점검:

| 스펙 항목 | Task |
|-----------|------|
| SQLite 스키마 + alembic | Task 4 (User만 — Plan 2/3에서 확장) |
| 라우터/서비스 폴더 구조 분리 | Task 5 (crawl), Task 11 (auth, users) |
| Google OAuth + 세션 쿠키 | Task 7-11 |
| 라우트 가드 미들웨어 | Task 9 (`require_login` 의존성) |
| 온보딩 화면 | Task 12 (API) + Task 14 (UI) |
| 시크릿 암호화 | Task 2 + Task 11 service.save_onboarding + Task 12 |
| 화이트리스트 검사 | Task 7 + Task 11 callback |
| 기존 코드 정돈 (중복 라우트, CORS, 포트, debug 가드, 추상 시그니처) | Task 5, Task 6, Task 15 |
| 회귀 방지 (익명 크롤 동작) | Task 5 회귀 테스트 |

스펙 11절의 "사용자별 시트 자동 생성"은 1차 비목표로 명시되어 있어 본 plan 범위 밖. 사용자가 만든 시트 URL을 입력하는 방식만 구현됨.

Plan 2/3에서 다룰 항목 (Plan 1 미포함, 의도적):
- 다른 모델 (`schedule_jobs`, `personal_blacklist`, `team_blacklist`, `send_history`, `run_logs`, `validation_cache`)
- EmailValidator, BlacklistService, DedupService, HistoryService, SmartleadClient
- 캠페인 드롭다운·푸시 다이얼로그
- APScheduler, ScheduleRunner, CircuitBreaker, PusherWorker
- SheetSyncWorker
- Smartlead 바운스 webhook
- 알림 이메일 모듈
- E2E Playwright

---

## Plan 1 완료 정의 (Definition of Done)

- [ ] `pytest -v` 전체 통과 (회귀 + 신규 단위/통합).
- [ ] `alembic upgrade head` 가 빈 DB에 적용되어 `users` 테이블 생성.
- [ ] 익명 사용자가 메인 페이지에서 크롤링·CSV·시트 export 가능 (기존 동작 회귀 없음).
- [ ] Google OAuth 로그인 후 세션 30일 유지.
- [ ] 화이트리스트 미설정 시 모든 Google 계정 허용 / 설정 시 도메인+이메일 OR 매칭.
- [ ] 온보딩 화면에서 시트 URL + Smartlead 키 입력·저장 가능, DB에 키는 암호화되어 저장.
- [ ] `/api/users/me` 가 마스킹된 키와 has_smartlead_key 플래그 반환.
- [ ] 로그아웃이 세션 쿠키 삭제.
- [ ] `Procfile` / Railway 배포 시그니처 변경 없음 (`server:app` 그대로).
- [ ] 기존 코드 리뷰 이슈 4건 해결: 중복 export 라우트, CORS 모순, 포트 불일치, debug 라우트 노출.
