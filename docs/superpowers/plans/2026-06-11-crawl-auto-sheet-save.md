# 크롤링 결과 자동 시트 저장 + 접근 보호 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 수동 크롤링 결과를 서버에 고정된 구글 시트에 자동 저장하고, 공유 비밀번호로 앱 전체를 보호한다.

**Architecture:** 시트 URL을 `state.db`의 `EngineState`(key/value)에 저장하고, 모든 보호 API는 `Authorization: Bearer` 토큰을 요구한다. 프론트는 첫 접속 시 비밀번호 게이트를 거쳐 토큰을 받고 `localStorage`에 저장한 뒤, 크롤링 완료 시 자동으로 export를 호출한다.

**Tech Stack:** FastAPI, SQLAlchemy(엔진 state.db), gspread, Vanilla JS, pytest + FastAPI TestClient

설계 문서: `docs/superpowers/specs/2026-06-11-crawl-auto-sheet-save-design.md`

---

## File Structure

**신규 생성:**
- `engine/kv.py` — `EngineState` 위에 얹은 `get_setting`/`set_setting` 헬퍼. 책임: key/value 설정 저장소 접근.
- `auth.py` (루트) — 비밀번호→토큰 변환·검증. 책임: 접근 보호 로직(엔드포인트·env와 분리된 순수 함수 중심).
- `tests/test_kv.py`, `tests/test_auth.py`, `tests/test_api_auth.py`, `tests/test_api_settings.py`, `tests/test_api_export.py`

**수정:**
- `server.py` — `/api/login`, `/api/settings`(GET/POST) 추가, `require_token`·`get_session` 의존성, `/api/export/sheet`가 kv에서 URL 읽도록 변경, 크롤·config 엔드포인트 보호.
- `static/index.html` — 비밀번호 게이트 오버레이 + 설정 모달(기존 구글 시트 모달 대체).
- `static/app.js` — 토큰 처리/`authFetch`, 설정 로드·저장, 크롤 완료 시 자동 export.
- `requirements.txt` — 변경 없음(httpx 이미 존재 → TestClient 사용 가능).

---

## Task 1: kv 설정 헬퍼 (`get_setting`/`set_setting`)

**Files:**
- Create: `engine/kv.py`
- Test: `tests/test_kv.py`

- [ ] **Step 1: Write the failing test**

`tests/test_kv.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from engine.db import Base
import engine.models  # noqa: F401
from engine.kv import get_setting, set_setting


@pytest.fixture
def session():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


def test_get_missing_returns_none(session):
    assert get_setting(session, "crawl_sheet_url") is None


def test_set_then_get(session):
    set_setting(session, "crawl_sheet_url", "https://docs.google.com/spreadsheets/d/abc")
    session.commit()
    assert get_setting(session, "crawl_sheet_url") == "https://docs.google.com/spreadsheets/d/abc"


def test_set_overwrites(session):
    set_setting(session, "crawl_sheet_url", "old")
    session.commit()
    set_setting(session, "crawl_sheet_url", "new")
    session.commit()
    assert get_setting(session, "crawl_sheet_url") == "new"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_kv.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.kv'`

- [ ] **Step 3: Write minimal implementation**

`engine/kv.py`:

```python
"""Key/value settings stored on top of EngineState (state.db)."""
from typing import Optional

from sqlalchemy.orm import Session

from engine.models import EngineState


def get_setting(session: Session, key: str) -> Optional[str]:
    row = session.get(EngineState, key)
    return row.value if row else None


def set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(EngineState, key)
    if row:
        row.value = value
    else:
        session.add(EngineState(key=key, value=value))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_kv.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/kv.py tests/test_kv.py
git commit -m "feat(kv): add EngineState get_setting/set_setting helpers"
```

---

## Task 2: 접근 보호 모듈 (`auth.py`)

**Files:**
- Create: `auth.py`
- Test: `tests/test_auth.py`

토큰은 `sha256(APP_PASSWORD + 고정 솔트)`. `APP_PASSWORD`는 호출 시점에 `os.getenv`로 읽는다(테스트에서 monkeypatch 가능, import 시점 고정 금지). 미설정이면 보호 비활성.

- [ ] **Step 1: Write the failing test**

`tests/test_auth.py`:

```python
import auth


def test_protection_disabled_when_no_password(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    assert auth.protection_enabled() is False
    assert auth.verify_token("anything") is False
    assert auth.expected_token() is None


def test_make_and_verify_token(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    token = auth.make_token("secret123")
    assert auth.protection_enabled() is True
    assert auth.verify_token(token) is True
    assert auth.verify_token("wrong") is False


def test_check_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    assert auth.check_password("secret123") is True
    assert auth.check_password("nope") is False


def test_token_changes_with_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "a")
    token_a = auth.make_token("a")
    monkeypatch.setenv("APP_PASSWORD", "b")
    assert auth.verify_token(token_a) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auth'`

- [ ] **Step 3: Write minimal implementation**

`auth.py`:

```python
"""Shared-password access protection (single user)."""
import hashlib
import hmac
import os
from typing import Optional

_SALT = "emailmak-access-v1"


def _password() -> Optional[str]:
    pw = os.getenv("APP_PASSWORD")
    return pw or None


def protection_enabled() -> bool:
    return _password() is not None


def make_token(password: str) -> str:
    return hashlib.sha256((password + _SALT).encode()).hexdigest()


def expected_token() -> Optional[str]:
    pw = _password()
    return make_token(pw) if pw else None


def verify_token(token: str) -> bool:
    exp = expected_token()
    if exp is None:
        return False
    return hmac.compare_digest(token or "", exp)


def check_password(password: str) -> bool:
    pw = _password()
    return pw is not None and hmac.compare_digest(password or "", pw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_auth.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add auth.py tests/test_auth.py
git commit -m "feat(auth): add shared-password token helpers"
```

---

## Task 3: `/api/login` + `require_token`/`get_session` 의존성

**Files:**
- Modify: `server.py`
- Test: `tests/test_api_auth.py`

세션 주입용 `get_session` 의존성과 토큰 검증용 `require_token` 의존성을 추가하고, `/api/login`을 만든다. 테스트는 `TestClient`를 컨텍스트 매니저 없이 생성하여 startup 이벤트(엔진 스케줄러)를 건드리지 않는다.

- [ ] **Step 1: Write the failing test**

`tests/test_api_auth.py`:

```python
from fastapi.testclient import TestClient

import server


def test_login_success(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    client = TestClient(server.app)
    resp = client.post("/api/login", json={"password": "secret123"})
    assert resp.status_code == 200
    assert resp.json()["token"]


def test_login_wrong_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    client = TestClient(server.app)
    resp = client.post("/api/login", json={"password": "nope"})
    assert resp.status_code == 401


def test_login_no_protection_returns_empty_token(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    client = TestClient(server.app)
    resp = client.post("/api/login", json={"password": ""})
    assert resp.status_code == 200
    assert resp.json()["token"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api_auth.py -v`
Expected: FAIL — `/api/login` 없음 → 404

- [ ] **Step 3: Write minimal implementation**

`server.py` 상단 import 영역에 추가:

```python
from fastapi import Depends, Header
from sqlalchemy.orm import Session

import auth
from engine.kv import get_setting, set_setting
```

(이미 `from fastapi import FastAPI, HTTPException`가 있으면 같은 줄에 `Depends, Header`를 합쳐도 됨.)

`server.py`에 의존성과 로그인 엔드포인트 추가 (CORS 설정 아래, `/api/crawl` 위 아무 곳):

```python
def get_session() -> Session:
    session = EngineSessionLocal()
    try:
        yield session
    finally:
        session.close()


def require_token(authorization: str = Header(default="")):
    if not auth.protection_enabled():
        return
    token = authorization.removeprefix("Bearer ").strip()
    if not auth.verify_token(token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")


class LoginRequest(BaseModel):
    password: str = ""


@app.post("/api/login")
async def login(request: LoginRequest):
    if not auth.protection_enabled():
        return {"token": ""}
    if not auth.check_password(request.password):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    return {"token": auth.make_token(request.password)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api_auth.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_api_auth.py
git commit -m "feat(api): add /api/login and token/session dependencies"
```

---

## Task 4: `/api/settings` GET/POST

**Files:**
- Modify: `server.py`
- Test: `tests/test_api_settings.py`

저장 시 시트 열림 검증을 위해 `GoogleSheetExporter`를 사용하지만, 테스트에서는 `server.GoogleSheetExporter`를 monkeypatch로 가짜 객체로 교체하고, `get_session`을 in-memory 세션으로 override한다.

- [ ] **Step 1: Write the failing test**

`tests/test_api_settings.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import server
from engine.db import Base
import engine.models  # noqa: F401


@pytest.fixture
def client_and_session(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)  # 보호 비활성으로 단순화
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)
    s = Session()

    def _override():
        yield s

    server.app.dependency_overrides[server.get_session] = _override
    client = TestClient(server.app)
    try:
        yield client, s, monkeypatch
    finally:
        server.app.dependency_overrides.clear()
        s.close()
        eng.dispose()


class _FakeExporter:
    opened = []

    def get_service_email(self):
        return "bot@project.iam.gserviceaccount.com"

    def authenticate(self):
        pass

    @property
    def client(self):
        return self

    def open_by_url(self, url):
        if "fail" in url:
            raise Exception("no access")
        _FakeExporter.opened.append(url)
        return object()


def test_get_settings_empty(client_and_session):
    client, _, _ = client_and_session
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["sheet_url"] is None


def test_post_then_get_settings(client_and_session):
    client, _, monkeypatch = client_and_session
    monkeypatch.setattr(server, "GoogleSheetExporter", _FakeExporter)
    url = "https://docs.google.com/spreadsheets/d/abc123"
    resp = client.post("/api/settings", json={"sheet_url": url})
    assert resp.status_code == 200
    assert client.get("/api/settings").json()["sheet_url"] == url


def test_post_invalid_url(client_and_session):
    client, _, monkeypatch = client_and_session
    monkeypatch.setattr(server, "GoogleSheetExporter", _FakeExporter)
    resp = client.post("/api/settings", json={"sheet_url": "https://example.com/x"})
    assert resp.status_code == 400


def test_post_unopenable_sheet(client_and_session):
    client, _, monkeypatch = client_and_session
    monkeypatch.setattr(server, "GoogleSheetExporter", _FakeExporter)
    url = "https://docs.google.com/spreadsheets/d/fail"
    resp = client.post("/api/settings", json={"sheet_url": url})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api_settings.py -v`
Expected: FAIL — `/api/settings` 없음 → 404 (또는 `server.get_session` AttributeError이면 Task 3 누락)

- [ ] **Step 3: Write minimal implementation**

`server.py`에 추가:

```python
class SettingsRequest(BaseModel):
    sheet_url: str


@app.get("/api/settings")
async def read_settings(session: Session = Depends(get_session), _=Depends(require_token)):
    return {
        "sheet_url": get_setting(session, "crawl_sheet_url"),
        "service_email": GoogleSheetExporter().get_service_email(),
    }


@app.post("/api/settings")
async def write_settings(
    request: SettingsRequest,
    session: Session = Depends(get_session),
    _=Depends(require_token),
):
    url = request.sheet_url.strip()
    if not url.startswith("https://docs.google.com/spreadsheets/"):
        raise HTTPException(status_code=400, detail="올바른 구글 시트 URL이 아닙니다.")
    exporter = GoogleSheetExporter()
    try:
        exporter.authenticate()
        exporter.client.open_by_url(url)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="시트를 열 수 없습니다. 봇 계정을 편집자로 초대했는지 확인하세요.",
        )
    set_setting(session, "crawl_sheet_url", url)
    session.commit()
    return {"success": True, "sheet_url": url}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api_settings.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_api_settings.py
git commit -m "feat(api): add /api/settings get/save with sheet validation"
```

---

## Task 5: `/api/export/sheet`가 서버 저장 URL 사용

**Files:**
- Modify: `server.py`
- Test: `tests/test_api_export.py`

export가 더 이상 요청 body의 `sheet_url`을 쓰지 않고 kv에서 읽는다. `ExportRequest.sheet_url`은 하위 호환을 위해 선택값으로 남기되 무시한다.

- [ ] **Step 1: Write the failing test**

`tests/test_api_export.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import server
from engine.db import Base
import engine.models  # noqa: F401
from engine.kv import set_setting


@pytest.fixture
def client_and_session(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)
    s = Session()
    server.app.dependency_overrides[server.get_session] = lambda: iter([s])
    client = TestClient(server.app)
    try:
        yield client, s, monkeypatch
    finally:
        server.app.dependency_overrides.clear()
        s.close()
        eng.dispose()


class _FakeExporter:
    used_url = None

    def export_to_sheet(self, sheet_url, data, keyword, source):
        _FakeExporter.used_url = sheet_url
        return True, f"saved {len(data)} rows"


def test_export_without_configured_sheet_400(client_and_session):
    client, _, _ = client_and_session
    resp = client.post("/api/export/sheet", json={"companies": [], "keyword": "k", "source": "사람인"})
    assert resp.status_code == 400


def test_export_uses_server_stored_url(client_and_session):
    client, s, monkeypatch = client_and_session
    set_setting(s, "crawl_sheet_url", "https://docs.google.com/spreadsheets/d/stored")
    s.commit()
    monkeypatch.setattr(server, "GoogleSheetExporter", _FakeExporter)
    resp = client.post(
        "/api/export/sheet",
        json={"companies": [{"company_name": "A"}], "keyword": "k", "source": "사람인",
              "sheet_url": "https://docs.google.com/spreadsheets/d/IGNORED"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert _FakeExporter.used_url == "https://docs.google.com/spreadsheets/d/stored"
```

(`get_session` override가 generator를 기대하므로 `lambda: iter([s])` 사용 — Task 4의 `_override` 형태와 동일한 효과.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api_export.py -v`
Expected: FAIL — 현재 export는 body의 `sheet_url`을 쓰고 kv 미사용 → `used_url`이 stored가 아니거나 400 미발생

- [ ] **Step 3: Write minimal implementation**

`server.py`의 `ExportRequest`에서 `sheet_url`을 선택값으로 변경:

```python
class ExportRequest(BaseModel):
    """구글 시트 내보내기 요청 모델 (sheet_url은 무시됨 — 서버 저장값 사용)"""
    companies: List[Dict[str, Any]]
    keyword: str = "검색어없음"
    source: str = "기타"
    sheet_url: Optional[str] = None  # 하위 호환용, 사용 안 함
```

`export_sheet` 핸들러를 교체:

```python
@app.post("/api/export/sheet")
async def export_sheet(
    request: ExportRequest,
    session: Session = Depends(get_session),
    _=Depends(require_token),
):
    """구글 시트로 데이터 내보내기 (서버에 저장된 시트 URL 사용)"""
    sheet_url = get_setting(session, "crawl_sheet_url")
    if not sheet_url:
        raise HTTPException(status_code=400, detail="먼저 설정에서 시트를 지정하세요.")
    try:
        exporter = GoogleSheetExporter()
        success, message = exporter.export_to_sheet(
            sheet_url, request.companies, request.keyword, request.source
        )
        if success:
            return {"success": True, "message": message}
        raise HTTPException(status_code=500, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api_export.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_api_export.py
git commit -m "feat(api): export uses server-stored sheet url"
```

---

## Task 6: 크롤·config 엔드포인트 보호

**Files:**
- Modify: `server.py`
- Test: `tests/test_api_auth.py` (테스트 추가)

`/api/crawl`, `/api/crawl/stream`, `/api/config/google-sheet`에 `require_token`을 부착한다.

- [ ] **Step 1: Write the failing test**

`tests/test_api_auth.py` 끝에 추가:

```python
def test_crawl_requires_token_when_protected(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    client = TestClient(server.app)
    resp = client.post("/api/crawl", json={"keyword": "x"})
    assert resp.status_code == 401


def test_config_requires_token_when_protected(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    client = TestClient(server.app)
    resp = client.get("/api/config/google-sheet")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api_auth.py -v`
Expected: 두 새 테스트 FAIL (현재 보호 없음 → 200/422/500)

- [ ] **Step 3: Write minimal implementation**

`server.py`의 해당 핸들러 시그니처에 `require_token` 의존성 추가:

```python
@app.post("/api/crawl")
async def crawl(request: CrawlRequest, _=Depends(require_token)):
    ...

@app.post("/api/crawl/stream")
async def crawl_stream(request: CrawlRequest, _=Depends(require_token)):
    ...

@app.get("/api/config/google-sheet")
async def get_google_sheet_config(_=Depends(require_token)):
    ...
```

(본문은 그대로. 시그니처에 `_=Depends(require_token)`만 추가.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api_auth.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_api_auth.py
git commit -m "feat(api): protect crawl and config endpoints with token"
```

---

## Task 7: 프론트 비밀번호 게이트 + authFetch

**Files:**
- Modify: `static/index.html`, `static/app.js`

프론트 작업은 JS 테스트 하니스가 없어 수동 검증한다.

- [ ] **Step 1: index.html에 게이트 오버레이 추가**

`<body>` 바로 다음, `<div class="container">` 앞에 삽입:

```html
<!-- 비밀번호 게이트 -->
<div id="authGate" class="modal hidden">
    <div class="modal-overlay"></div>
    <div class="modal-content">
        <h3>🔒 접근 비밀번호</h3>
        <p class="modal-desc">이 도구를 사용하려면 비밀번호를 입력하세요.</p>
        <input type="password" id="authPasswordInput" placeholder="비밀번호"
            class="form-input" style="width: 100%; margin: 10px 0;">
        <div class="modal-actions" style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 15px;">
            <button id="authSubmitBtn" class="btn-primary">확인</button>
        </div>
    </div>
</div>
```

- [ ] **Step 2: app.js에 토큰/authFetch/게이트 로직 추가**

`app.js` 최상단(다른 const 선언 근처)에 추가:

```javascript
const TOKEN_KEY = 'access_token';
function getToken() { return localStorage.getItem(TOKEN_KEY) || ''; }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }

async function authFetch(url, options = {}) {
    const opts = { ...options };
    opts.headers = { ...(opts.headers || {}), 'Authorization': 'Bearer ' + getToken() };
    const res = await fetch(url, opts);
    if (res.status === 401) {
        showAuthGate();
        throw new Error('인증이 필요합니다');
    }
    return res;
}

function showAuthGate() {
    document.getElementById('authGate').classList.remove('hidden');
}
function hideAuthGate() {
    document.getElementById('authGate').classList.add('hidden');
}

async function submitPassword() {
    const pw = document.getElementById('authPasswordInput').value;
    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pw }),
        });
        if (!res.ok) { showToast('비밀번호가 올바르지 않습니다.', 'error'); return; }
        const data = await res.json();
        setToken(data.token);
        hideAuthGate();
        document.getElementById('authPasswordInput').value = '';
        await loadSettings();  // Task 8에서 정의
    } catch (e) {
        showToast('로그인 오류가 발생했습니다.', 'error');
    }
}

// 첫 진입 시 토큰 유효성 확인 (보호 비활성이면 200, 토큰 없으면 401)
async function checkAuthOnLoad() {
    try {
        const res = await fetch('/api/settings', {
            headers: { 'Authorization': 'Bearer ' + getToken() },
        });
        if (res.status === 401) { showAuthGate(); return; }
        await loadSettings();  // Task 8
    } catch (e) {
        showAuthGate();
    }
}
```

- [ ] **Step 3: 기존 fetch 호출을 authFetch로 교체 + 초기화 연결**

`app.js`에서 다음 호출들을 `fetch(` → `authFetch(`로 변경:
- `/api/crawl/stream` 호출 (약 189행)
- `/api/export/sheet` 호출 (약 437행)
- `/api/config/google-sheet` 호출 (약 70행)

(단, `/api/login` 호출은 `fetch` 그대로 둔다 — authFetch는 401에서 게이트를 띄우므로 로그인엔 부적합.)

초기화 함수(이벤트 리스너 등록부, `init`/`DOMContentLoaded` 핸들러 끝)에 추가:

```javascript
document.getElementById('authSubmitBtn').addEventListener('click', submitPassword);
document.getElementById('authPasswordInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submitPassword();
});
checkAuthOnLoad();
```

- [ ] **Step 4: 수동 검증**

```bash
APP_PASSWORD=test123 ENGINE_ENABLED=0 .venv/bin/uvicorn server:app --port 8000
```

브라우저에서 `http://localhost:8000` 열기:
- 게이트가 떠야 함. 틀린 비번 → 토스트 에러. 맞는 비번(`test123`) → 게이트 닫힘.
- 새로고침 시 게이트 안 뜸(토큰 저장됨). `localStorage.removeItem('access_token')` 후 새로고침 → 게이트 다시 뜸.

- [ ] **Step 5: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(ui): add password gate and authFetch wrapper"
```

---

## Task 8: 프론트 설정 화면 (시트 지정)

**Files:**
- Modify: `static/index.html`, `static/app.js`

기존 "구글 시트" 모달을 "설정" 모달로 용도 변경: 봇 이메일 안내 + 시트 URL 1회 저장.

- [ ] **Step 1: index.html 수정 — 설정 버튼 + 모달 문구**

헤더(`<header class="header">`) 안 `subtitle` 아래에 설정 버튼 추가:

```html
<button id="settingsBtn" class="btn-secondary" style="margin-top: 10px;">⚙️ 설정</button>
```

기존 `<div id="sheetModal" ...>` 모달의 제목/문구를 설정용으로 교체하고 입력 id를 유지하되 버튼 텍스트를 "저장"으로 변경. `<h3>구글 시트로 내보내기</h3>`를 `<h3>설정 — 구글 시트 지정</h3>`로, `2. 데이터를 저장할 구글 시트 URL을 입력하세요.`는 그대로 두고, `<button id="sheetConfirmBtn" class="btn-primary">내보내기</button>`를 `저장`으로 변경. 현재 저장된 URL 표시용 안내를 입력칸 위에 추가:

```html
<p id="currentSheetInfo" class="modal-desc" style="font-size: 0.85rem; color: #a5b4fc;"></p>
```

결과 헤더(`results-meta`)의 `googleSheetBtn`(구글 시트)은 "지금 저장"으로 라벨 변경:

```html
<button id="googleSheetBtn" class="btn-success" style="background-color: #0F9D58; color: white;">
    <span>📊</span> 지금 저장
</button>
```

- [ ] **Step 2: app.js — loadSettings / saveSettings / 모달 연결**

```javascript
let configuredSheetUrl = null;

async function loadSettings() {
    try {
        const res = await authFetch('/api/settings');
        const data = await res.json();
        configuredSheetUrl = data.sheet_url;
        const info = document.getElementById('currentSheetInfo');
        if (info) {
            info.textContent = configuredSheetUrl
                ? '현재 시트: ' + configuredSheetUrl
                : '아직 시트가 지정되지 않았습니다.';
        }
        if (botEmailInput && data.service_email) botEmailInput.value = data.service_email;
    } catch (e) { /* authFetch가 게이트 처리 */ }
}

async function saveSettings() {
    const url = sheetUrlInput.value.trim();
    if (!url) { showToast('시트 URL을 입력하세요.', 'warning'); return; }
    sheetConfirmBtn.disabled = true;
    try {
        const res = await authFetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sheet_url: url }),
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast('시트가 저장되었습니다.', 'success');
            configuredSheetUrl = data.sheet_url;
            sheetModal.classList.add('hidden');
            sheetUrlInput.value = '';
        } else {
            showToast(data.detail || '저장에 실패했습니다.', 'error');
        }
    } catch (e) {
        showToast('저장 중 오류가 발생했습니다.', 'error');
    } finally {
        sheetConfirmBtn.disabled = false;
    }
}
```

초기화부 수정:
- `settingsBtn` 클릭 → 모달 열고 `loadSettings()` 호출:

```javascript
document.getElementById('settingsBtn').addEventListener('click', async () => {
    sheetModal.classList.remove('hidden');
    await loadSettings();
});
```

- 기존 `sheetConfirmBtn.addEventListener('click', exportToGoogleSheet);`를 `sheetConfirmBtn.addEventListener('click', saveSettings);`로 변경.

- [ ] **Step 3: 수동 검증**

서버 실행 후 로그인 → ⚙️ 설정 클릭:
- 봇 이메일 표시, "아직 시트가 지정되지 않았습니다." 표시.
- 올바른 시트 URL(봇을 편집자로 초대한 시트) 입력 → 저장 성공 토스트. 다시 설정 열면 "현재 시트: ..." 표시.
- 잘못된 URL 입력 → 에러 토스트(400).

- [ ] **Step 4: Commit**

```bash
git add static/index.html static/app.js
git commit -m "feat(ui): settings screen to configure target sheet"
```

---

## Task 9: 크롤 완료 시 자동 저장

**Files:**
- Modify: `static/app.js`

SSE `complete` 처리부에서 시트가 지정돼 있으면 자동 export, 아니면 안내. 기존 "지금 저장"(`googleSheetBtn`)은 수동 저장용으로 export 호출(URL 미전송).

- [ ] **Step 1: app.js — 자동/수동 export 함수 통일**

기존 `exportToGoogleSheet()`를 시트 URL 미전송 + 모달 비의존 형태로 교체:

```javascript
async function saveResultsToSheet(isAuto) {
    if (results.length === 0) {
        if (!isAuto) showToast('내보낼 결과가 없습니다.', 'warning');
        return;
    }
    if (!configuredSheetUrl) {
        showToast('먼저 ⚙️ 설정에서 시트를 지정하세요.', 'warning');
        return;
    }
    const keyword = document.getElementById('keyword').value.trim() || '검색어없음';
    const sourceSelect = document.getElementById('source');
    const sourceText = sourceSelect.options[sourceSelect.selectedIndex].text;
    try {
        const res = await authFetch('/api/export/sheet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ companies: results, keyword, source: sourceText }),
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast((isAuto ? '자동 저장됨: ' : '') + data.message, 'success');
        } else {
            showToast(data.detail || '저장에 실패했습니다.', 'error');
        }
    } catch (e) {
        showToast('서버 연결 오류가 발생했습니다.', 'error');
    }
}
```

- [ ] **Step 2: SSE complete 처리부에서 자동 호출**

`app.js`에서 `'complete'` 타입을 처리하는 부분(크롤 종료 처리) 끝에 추가:

```javascript
// 크롤 완료 → 시트 자동 저장
saveResultsToSheet(true);
```

`googleSheetBtn`(지금 저장) 리스너를 교체 — 기존 모달 오픈 로직 제거하고:

```javascript
googleSheetBtn.addEventListener('click', () => saveResultsToSheet(false));
```

- [ ] **Step 3: 수동 검증**

- 시트 지정된 상태로 크롤링 → 완료되면 자동으로 "자동 저장됨: ..." 토스트, 구글 시트에 새 탭 + 발송명단 누적 확인.
- 시트 미지정 상태로 크롤링 → "먼저 ⚙️ 설정에서 시트를 지정하세요." 안내, 결과는 화면에 유지.
- "지금 저장" 버튼 → 동일 시트에 재저장.

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): auto-save crawl results to configured sheet"
```

---

## Task 10: 배포 문서 + 전체 회귀

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README에 env 안내 추가**

`README.md`의 환경변수/배포 섹션에 추가(없으면 "## 환경변수" 섹션 신설):

```markdown
### 접근 보호

- `APP_PASSWORD`: 앱 접근 비밀번호. **배포 시 반드시 설정**하세요. 미설정이면 접근 보호가 비활성화되어 누구나 접속할 수 있습니다(로컬 개발 전용).

### 시트 저장

- 크롤링 결과 저장 시트는 앱 안 **⚙️ 설정**에서 지정합니다(서버 `state.db`에 저장, 모든 기기 공유).
- 지정한 시트에 서비스 계정(봇) 이메일을 **편집자**로 초대해야 합니다. 봇 이메일은 설정 화면에 표시됩니다.
```

- [ ] **Step 2: 전체 테스트 실행**

Run: `.venv/bin/pytest tests/ -v`
Expected: 기존 엔진 테스트 + 신규 테스트(kv 3, auth 4, api_auth 5, api_settings 4, api_export 2) 전부 PASS

- [ ] **Step 3: 서버 기동 스모크 테스트**

```bash
APP_PASSWORD=test123 ENGINE_ENABLED=0 .venv/bin/uvicorn server:app --port 8000
```
브라우저: 게이트 → 로그인 → 설정에서 시트 지정 → 크롤링 → 자동 저장까지 1회 end-to-end 확인.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: APP_PASSWORD and sheet settings deployment notes"
```

---

## Self-Review 결과

**Spec coverage:**
- §4.1 접근 보호 → Task 2, 3, 6, 7 ✓
- §4.2 시트 저장/조회 → Task 1, 4, 8 ✓
- §4.3 자동 적재 → Task 5, 9 ✓
- §4.4 UX 변화(모달→설정) → Task 8 ✓
- §5 에러 처리 → Task 4(잘못된 URL/시트 못 엶), 5(미지정 400), 9(미지정 안내) ✓
- §6 테스트 → Task 1~6 ✓
- §8 구현 순서 일치 ✓

**Placeholder scan:** 모든 코드 단계에 실제 코드 포함. "TBD/TODO/적절히 처리" 없음 ✓

**Type consistency:** `get_setting`/`set_setting`(Task 1) ↔ Task 4·5 사용 일치. `require_token`/`get_session`(Task 3) ↔ Task 4·5·6 사용 일치. `authFetch`/`loadSettings`/`configuredSheetUrl`/`saveResultsToSheet`(Task 7·8·9) 명명 일관 ✓

**알려진 주의:** 프론트 행 번호(약 70/189/437행)는 참고치 — 실제 교체 시 호출 URL 문자열로 찾을 것.
