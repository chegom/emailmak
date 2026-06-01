# 시트 자동화 엔진 — Plan 2: 통합·오케스트레이션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Plan 1의 결정론적 코어(EngineSettings·state.db·EmailValidator·DedupStore)를 외부 연동(Sheets·Gemini·Smartlead)과 스케줄러로 조립해, 3일 주기 무인 콜드메일 자동화를 완성한다.

**Architecture:** 모든 신규 코드는 `engine/` 패키지(=`app/` 비의존)에 둔다. 외부 I/O 클라이언트(gspread/httpx/google-genai)는 생성자 주입으로 받아 단위 테스트에서 가짜 객체/respx로 대체한다. 오케스트레이션은 `RunPipeline`이 담당하고 `HourlyTick`(APScheduler)이 트리거한다.

**Tech Stack:** Python, SQLAlchemy 2.0, httpx + respx, gspread, google-genai, APScheduler, pytest/pytest-asyncio, freezegun.

**선행:** `docs/superpowers/plans/2026-06-01-plan-1-engine-core.md` (완료 — `engine/settings.py`,`engine/db.py`,`engine/models.py`,`engine/validator.py`,`engine/dedup.py`).
**스펙:** `docs/superpowers/specs/2026-06-01-sheet-driven-smartlead-automation-design.md`.

---

## 데이터 계약 (Plan 1 산출물과의 정합 — 전 태스크 공통)

```
# EmailValidator.validate(companies) -> ValidationResult
#   companies: [{company_name, emails:[str], job_title, company_url, homepage, source}]
#   result.valid: [{company_name, email, domain, is_role, job_title, source}]
#   result.dropped: [{email, reason}] ; result.pass_rate: float
# DedupStore: filter_new(records)->records ; mark_pushed(records, campaign_id) ; backfill(records)
# 검증 valid 레코드 = Smartlead 리드의 입력 단위. 'email','company_name','job_title','source','domain','is_role' 보유.
```

**시트 헤더 (정확히 이 한글 키를 사용):**
- `⚙️설정`: `산업군, 사이트, 캠페인ID, 주기(일), 미리채울회수, 페이지, 활성화`
- `📅키워드스케줄`: `예정일시, 산업군, 키워드, 출처, 상태`
- `발송내역`: `기록일시, 실행ID, 회사명, 이메일, 산업군, 키워드, 사이트, 캠페인ID, 검증결과, 역할주소여부, push_status, accepted_at, 응답요약`
- `⚠️경고`: `일시, 실행ID, 종류, 상세, 수치`

---

## File Structure (Plan 2 범위)

| 파일 | 책임 |
|------|------|
| `engine/crawler_service.py` | `CrawlerService` — 사이트별 크롤러 호출 + source 부착 |
| `engine/smartlead.py` | `SmartleadClient` — 리드 배치 푸시 + 통계 조회 |
| `engine/gemini.py` | `GeminiClient` — Gemini로 키워드 생성 |
| `engine/keywords.py` | `KeywordResolver` — 수동 우선/비면 Gemini |
| `engine/sheets.py` | `SheetControl` — gspread 읽기/쓰기/상태갱신 |
| `engine/planner.py` | `SchedulePlanner` — 예정표 top-up |
| `engine/alerts.py` | `AlertMonitor` — delta 기반 bounce 경고 + suspend |
| `engine/pipeline.py` | `RunPipeline` — 한 행 실행 조립 |
| `engine/scheduler.py` | `HourlyTick` — APScheduler 등록 + 도래행 실행 + 락 |
| `server.py` | (수정) 시작 시 스케줄러 등록 + `/healthz` |
| `requirements.txt` | apscheduler, google-genai 추가 |

**원칙:** 외부 클라이언트는 생성자 주입. `engine/`은 `app/`·`server.py`를 import 하지 않는다(역방향만 허용: server.py가 engine을 등록).

---

## Task 1: SmartleadClient (리드 배치 푸시 + 통계)

**Files:**
- Create: `engine/smartlead.py`
- Modify: `requirements.txt` (httpx 이미 있음 — 변경 없음; 확인만)
- Test: `tests/engine/test_smartlead.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/engine/test_smartlead.py`:

```python
import httpx
import respx

from engine.smartlead import SmartleadClient

BASE = "https://server.smartlead.ai/api/v1"


def _records(*emails):
    return [{"email": e, "company_name": "C", "job_title": "t",
             "source": "saramin", "domain": e.split("@")[1], "is_role": False} for e in emails]


@respx.mock
def test_push_leads_batches_and_marks_accepted():
    route = respx.post(f"{BASE}/campaigns/42/leads").mock(
        return_value=httpx.Response(200, json={"upload_count": 2})
    )
    client = SmartleadClient(api_key="k", client=httpx.Client())
    result = client.push_leads("42", _records("a@x.com", "b@y.com"))
    assert route.called
    sent_body = route.calls[0].request
    assert "api_key=k" in str(sent_body.url)
    assert {r["email"] for r in result.accepted} == {"a@x.com", "b@y.com"}
    assert result.failed == []


@respx.mock
def test_push_leads_splits_over_100():
    respx.post(f"{BASE}/campaigns/42/leads").mock(return_value=httpx.Response(200, json={}))
    client = SmartleadClient(api_key="k", client=httpx.Client())
    recs = _records(*[f"u{i}@x.com" for i in range(250)])
    client.push_leads("42", recs)
    assert respx.calls.call_count == 3  # 100+100+50


@respx.mock
def test_push_leads_4xx_marks_failed():
    respx.post(f"{BASE}/campaigns/42/leads").mock(return_value=httpx.Response(400, json={"message": "bad"}))
    client = SmartleadClient(api_key="k", client=httpx.Client())
    result = client.push_leads("42", _records("a@x.com"))
    assert result.accepted == []
    assert [r["email"] for r in result.failed] == ["a@x.com"]


@respx.mock
def test_get_campaign_stats():
    respx.get(f"{BASE}/campaigns/42/analytics").mock(
        return_value=httpx.Response(200, json={"sent_count": "100", "bounce_count": "7"})
    )
    client = SmartleadClient(api_key="k", client=httpx.Client())
    stats = client.get_campaign_stats("42")
    assert stats == {"sent": 100, "bounced": 7}
```

- [ ] **Step 2: 실패 확인** — Run: `.venv/bin/pytest tests/engine/test_smartlead.py -v` → FAIL (ModuleNotFoundError).

- [ ] **Step 3: 구현**

Create `engine/smartlead.py`:

```python
"""Smartlead 리드 추가 + 캠페인 통계 클라이언트. 공식 파라미터(스펙 §9) 사용."""
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

BASE_URL = "https://server.smartlead.ai/api/v1"
BATCH = 100
PUSH_SETTINGS = {
    "ignore_global_block_list": True,
    "ignore_unsubscribe_list": True,
    "ignore_duplicate_leads_in_other_campaign": True,
}


@dataclass
class PushResult:
    accepted: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    note: str = ""


def _to_lead(rec: dict) -> dict:
    return {
        "email": rec["email"],
        "company_name": rec.get("company_name") or "",
        "custom_fields": {
            "job_title": rec.get("job_title") or "",
            "source": rec.get("source") or "",
        },
    }


class SmartleadClient:
    def __init__(self, api_key: str, base_url: str = BASE_URL,
                 client: Optional[httpx.Client] = None, sleep=time.sleep,
                 max_retries: int = 5):
        self.api_key = api_key
        self.base_url = base_url
        self.client = client or httpx.Client(timeout=30.0)
        self.sleep = sleep
        self.max_retries = max_retries

    def _params(self) -> dict:
        return {"api_key": self.api_key}

    def push_leads(self, campaign_id: str, records: list) -> PushResult:
        result = PushResult()
        url = f"{self.base_url}/campaigns/{campaign_id}/leads"
        for i in range(0, len(records), BATCH):
            batch = records[i:i + BATCH]
            body = {"lead_list": [_to_lead(r) for r in batch], "settings": PUSH_SETTINGS}
            try:
                resp = self._post_with_retry(url, body)
            except httpx.HTTPError as e:
                result.failed.extend(batch)
                result.note = f"http_error: {e}"
                continue
            if resp.status_code // 100 == 2:
                result.accepted.extend(batch)
            else:
                result.failed.extend(batch)
                result.note = f"{resp.status_code}: {resp.text[:200]}"
        return result

    def _post_with_retry(self, url: str, body: dict) -> httpx.Response:
        for attempt in range(self.max_retries):
            resp = self.client.post(url, params=self._params(), json=body)
            if resp.status_code in (429, 500, 502, 503) and attempt < self.max_retries - 1:
                self.sleep(min(60, 2 ** attempt))
                continue
            return resp
        return resp

    def get_campaign_stats(self, campaign_id: str) -> dict:
        url = f"{self.base_url}/campaigns/{campaign_id}/analytics"
        resp = self.client.get(url, params=self._params())
        resp.raise_for_status()
        data = resp.json()
        # 필드명은 통합 시 실제 응답으로 확정 — 흔한 키를 폭넓게 수용
        sent = int(data.get("sent_count") or data.get("sent") or 0)
        bounced = int(data.get("bounce_count") or data.get("bounced") or data.get("bounces") or 0)
        return {"sent": sent, "bounced": bounced}
```

> **통합 검증 포인트:** `analytics` 엔드포인트의 실제 필드명(`sent_count`/`bounce_count`)은 첫 실연결 때 응답을 찍어 확정한다. 파서는 흔한 키를 모두 수용하도록 작성됨.

- [ ] **Step 4: 통과 확인** — Run: `.venv/bin/pytest tests/engine/test_smartlead.py -v` → PASS (4 passed).

- [ ] **Step 5: 커밋**

```bash
git add engine/smartlead.py tests/engine/test_smartlead.py
git commit -m "feat(engine): SmartleadClient — 리드 배치 푸시 + 통계 조회"
```

---

## Task 2: GeminiClient + KeywordResolver

**Files:**
- Create: `engine/gemini.py`, `engine/keywords.py`
- Modify: `requirements.txt` (google-genai 추가)
- Test: `tests/engine/test_keywords.py`

- [ ] **Step 1: requirements.txt에 추가** — `dnspython==2.6.1` 다음 줄에:

```
google-genai==0.3.0
apscheduler==3.10.4
```

Run: `.venv/bin/pip install google-genai==0.3.0 apscheduler==3.10.4`
> 설치 실패/버전 불일치 시 가장 가까운 안정 버전으로 맞추고 그 버전을 requirements에 기록 — 임의 추정 금지.

- [ ] **Step 2: 실패하는 테스트 작성**

Create `tests/engine/test_keywords.py`:

```python
from engine.gemini import GeminiClient
from engine.keywords import KeywordResolver


def test_gemini_parses_and_filters_avoid():
    # generate 콜백 주입 — 실제 API 호출 없음
    gen = lambda prompt: "3PL, 풀필먼트, WMS, 풀필먼트"
    client = GeminiClient(api_key="k", generate=gen)
    kws = client.generate_keywords("물류", avoid=["WMS"], n=5)
    assert kws == ["3PL", "풀필먼트"]  # 중복·avoid 제거


def test_gemini_respects_n():
    gen = lambda prompt: "a, b, c, d, e, f"
    client = GeminiClient(api_key="k", generate=gen)
    assert client.generate_keywords("x", avoid=[], n=3) == ["a", "b", "c"]


def test_resolver_uses_manual_keyword():
    resolver = KeywordResolver(gemini=None)
    kws, src = resolver.resolve(industry="물류", manual="3PL, 풀필먼트", avoid=[], n=5)
    assert kws == ["3PL", "풀필먼트"]
    assert src == "manual"


def test_resolver_falls_back_to_gemini():
    class FakeGemini:
        def generate_keywords(self, industry, avoid, n):
            return ["콜드체인"]
    resolver = KeywordResolver(gemini=FakeGemini())
    kws, src = resolver.resolve(industry="물류", manual="", avoid=[], n=5)
    assert kws == ["콜드체인"]
    assert src == "ai"
```

- [ ] **Step 3: 실패 확인** — `.venv/bin/pytest tests/engine/test_keywords.py -v` → FAIL.

- [ ] **Step 4: 구현**

Create `engine/gemini.py`:

```python
"""Gemini로 산업군→키워드 생성. generate 콜백 주입으로 테스트 가능."""
from typing import Callable, Optional

MODEL = "gemini-2.5-flash"


def _split(text: str) -> list:
    parts = []
    for chunk in text.replace("\n", ",").split(","):
        kw = chunk.strip().lstrip("-•").strip()
        if kw:
            parts.append(kw)
    return parts


class GeminiClient:
    def __init__(self, api_key: str, model: str = MODEL,
                 generate: Optional[Callable[[str], str]] = None):
        self.api_key = api_key
        self.model = model
        self._generate = generate or self._default_generate

    def _default_generate(self, prompt: str) -> str:
        from google import genai  # 지연 import
        client = genai.Client(api_key=self.api_key)
        resp = client.models.generate_content(model=self.model, contents=prompt)
        return resp.text or ""

    def generate_keywords(self, industry: str, avoid: list, n: int) -> list:
        avoid_txt = ", ".join(avoid) if avoid else "(없음)"
        prompt = (
            f"한국 채용사이트(사람인/잡코리아/원티드)에서 '{industry}' 산업군 기업을 "
            f"찾기 위한 검색 키워드를 {n}개 제안해줘. 회사가 채용공고에 쓸 법한 단어로. "
            f"다음 키워드는 제외: {avoid_txt}. "
            f"설명 없이 쉼표로 구분된 키워드만 출력."
        )
        raw = self._generate(prompt)
        avoid_set = {a.strip() for a in avoid}
        out, seen = [], set()
        for kw in _split(raw):
            if kw in avoid_set or kw in seen:
                continue
            seen.add(kw)
            out.append(kw)
            if len(out) >= n:
                break
        return out
```

Create `engine/keywords.py`:

```python
"""키워드 결정: 수동 입력 있으면 그대로(=manual), 비면 Gemini(=ai)."""
from typing import Optional


def _split(text: str) -> list:
    return [k.strip() for k in (text or "").replace("\n", ",").split(",") if k.strip()]


class KeywordResolver:
    def __init__(self, gemini=None):
        self.gemini = gemini

    def resolve(self, industry: str, manual: str, avoid: list, n: int):
        """returns (keywords: list[str], source: 'manual'|'ai')."""
        manual_kws = _split(manual)
        if manual_kws:
            return manual_kws, "manual"
        if self.gemini is None:
            return [], "ai"
        return self.gemini.generate_keywords(industry, avoid, n), "ai"
```

- [ ] **Step 5: 통과 확인** — `.venv/bin/pytest tests/engine/test_keywords.py -v` → PASS (4 passed).

- [ ] **Step 6: 커밋**

```bash
git add engine/gemini.py engine/keywords.py requirements.txt tests/engine/test_keywords.py
git commit -m "feat(engine): GeminiClient + KeywordResolver (수동 우선/비면 AI)"
```

---

## Task 3: SheetControl (gspread 읽기/쓰기/상태갱신)

**배경:** `utils/google_sheets.py`의 `GoogleSheetExporter`가 이미 gspread(`service_account_from_dict`, `open_by_url`, `worksheet`, `get_all_values`)를 쓴다. SheetControl은 **열린 spreadsheet 객체를 주입**받아 4개 탭을 다룬다(테스트는 가짜 spreadsheet).

**Files:**
- Create: `engine/sheets.py`
- Test: `tests/engine/test_sheets.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/engine/test_sheets.py`:

```python
from engine.sheets import SheetControl


class FakeWorksheet:
    def __init__(self, rows):
        self._records = rows
        self.appended = []
        self.updated = []

    def get_all_records(self):
        return list(self._records)

    def append_row(self, values, value_input_option="RAW"):
        self.appended.append(values)

    def update_cell(self, row, col, value):
        self.updated.append((row, col, value))


class FakeSpreadsheet:
    def __init__(self, tabs):
        self._tabs = tabs

    def worksheet(self, title):
        return self._tabs[title]


def test_read_settings_only_active():
    ws = FakeWorksheet([
        {"산업군": "물류", "사이트": "saramin", "캠페인ID": "42", "주기(일)": 3,
         "미리채울회수": 5, "페이지": "1-5", "활성화": "Y"},
        {"산업군": "헬스", "사이트": "wanted", "캠페인ID": "9", "주기(일)": 3,
         "미리채울회수": 5, "페이지": "", "활성화": "N"},
    ])
    sc = SheetControl(FakeSpreadsheet({"⚙️설정": ws}))
    settings = sc.read_settings()
    assert len(settings) == 1
    assert settings[0].industry == "물류"
    assert settings[0].campaign_id == "42"
    assert settings[0].interval_days == 3


def test_read_schedule_returns_row_numbers():
    ws = FakeWorksheet([
        {"예정일시": "2026-06-04", "산업군": "물류", "키워드": "3PL", "출처": "ai", "상태": "예정"},
    ])
    sc = SheetControl(FakeSpreadsheet({"📅키워드스케줄": ws}))
    rows = sc.read_schedule()
    assert rows[0].row_number == 2  # 헤더가 1행 → 데이터 첫 행은 2
    assert rows[0].keyword == "3PL"


def test_append_warning():
    ws = FakeWorksheet([])
    sc = SheetControl(FakeSpreadsheet({"⚠️경고": ws}))
    sc.append_warning(run_id="r1", kind="bounce_warn", detail="물류/42", value="6%")
    assert ws.appended[0][1:] == ["r1", "bounce_warn", "물류/42", "6%"]


def test_update_row_status():
    ws = FakeWorksheet([{"예정일시": "x", "산업군": "물류", "키워드": "", "출처": "ai", "상태": "예정"}])
    sc = SheetControl(FakeSpreadsheet({"📅키워드스케줄": ws}))
    sc.set_schedule_status(row_number=2, status="✅완료")
    # 상태는 5번째 열(E)
    assert (2, 5, "✅완료") in ws.updated
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/engine/test_sheets.py -v` → FAIL.

- [ ] **Step 3: 구현**

Create `engine/sheets.py`:

```python
"""컨트롤 시트(gspread) 읽기/쓰기. 열린 spreadsheet 주입 — 프로덕션은 open_control_sheet 사용."""
from dataclasses import dataclass
from datetime import datetime

TAB_SETTINGS = "⚙️설정"
TAB_SCHEDULE = "📅키워드스케줄"
TAB_HISTORY = "발송내역"
TAB_WARN = "⚠️경고"

# 📅키워드스케줄 열 순서 (1-indexed): 예정일시,산업군,키워드,출처,상태
SCHED_COL = {"예정일시": 1, "산업군": 2, "키워드": 3, "출처": 4, "상태": 5}


@dataclass
class JobSetting:
    industry: str
    sites: list
    campaign_id: str
    interval_days: int
    topup_count: int
    pages: str
    enabled: bool


@dataclass
class ScheduleRow:
    row_number: int
    when: str
    industry: str
    keyword: str
    source: str
    status: str


def open_control_sheet(credentials_json: str, sheet_url: str):
    import json
    import gspread
    client = gspread.service_account_from_dict(json.loads(credentials_json))
    return client.open_by_url(sheet_url)


class SheetControl:
    def __init__(self, spreadsheet):
        self.ss = spreadsheet

    def _ws(self, title):
        return self.ss.worksheet(title)

    def read_settings(self) -> list:
        out = []
        for r in self._ws(TAB_SETTINGS).get_all_records():
            if str(r.get("활성화", "")).strip().upper() != "Y":
                continue
            out.append(JobSetting(
                industry=str(r.get("산업군", "")).strip(),
                sites=[s.strip() for s in str(r.get("사이트", "")).split(",") if s.strip()],
                campaign_id=str(r.get("캠페인ID", "")).strip(),
                interval_days=int(r.get("주기(일)") or 3),
                topup_count=int(r.get("미리채울회수") or 5),
                pages=str(r.get("페이지", "") or "1-5").strip(),
                enabled=True,
            ))
        return out

    def read_schedule(self) -> list:
        rows = []
        for idx, r in enumerate(self._ws(TAB_SCHEDULE).get_all_records(), start=2):
            rows.append(ScheduleRow(
                row_number=idx,
                when=str(r.get("예정일시", "")).strip(),
                industry=str(r.get("산업군", "")).strip(),
                keyword=str(r.get("키워드", "")).strip(),
                source=str(r.get("출처", "")).strip(),
                status=str(r.get("상태", "")).strip(),
            ))
        return rows

    def append_schedule(self, when: str, industry: str, keyword: str, source: str, status: str = "예정"):
        self._ws(TAB_SCHEDULE).append_row([when, industry, keyword, source, status])

    def set_schedule_status(self, row_number: int, status: str):
        self._ws(TAB_SCHEDULE).update_cell(row_number, SCHED_COL["상태"], status)

    def set_schedule_keyword(self, row_number: int, keyword: str, source: str):
        ws = self._ws(TAB_SCHEDULE)
        ws.update_cell(row_number, SCHED_COL["키워드"], keyword)
        ws.update_cell(row_number, SCHED_COL["출처"], source)

    def append_history(self, run_id, company, email, industry, keyword, site,
                       campaign_id, verdict, is_role, push_status, accepted_at, note):
        self._ws(TAB_HISTORY).append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), run_id, company, email,
            industry, keyword, site, campaign_id, verdict, "Y" if is_role else "",
            push_status, accepted_at or "", note or "",
        ])

    def append_warning(self, run_id, kind, detail, value=""):
        self._ws(TAB_WARN).append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), run_id, kind, detail, str(value),
        ])
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest tests/engine/test_sheets.py -v` → PASS (4 passed).

- [ ] **Step 5: 커밋**

```bash
git add engine/sheets.py tests/engine/test_sheets.py
git commit -m "feat(engine): SheetControl — 4개 탭 읽기/쓰기/상태갱신"
```

---

## Task 4: SchedulePlanner (예정표 top-up)

**규칙(스펙 §3,§4.1):** 산업군별로 미래 `상태=예정` 행이 `미리채울회수(N)` 미만이면, 마지막 예정일 + `주기(일)` 간격으로 부족분을 생성한다. **키워드가 비어있지 않은 행·기존 예정 행은 건드리지 않는다.** 새 행 키워드는 Gemini로 채우고 회피목록 = 완료/기존 예정 키워드.

**Files:**
- Create: `engine/planner.py`
- Test: `tests/engine/test_planner.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/engine/test_planner.py`:

```python
from datetime import date

from engine.planner import SchedulePlanner
from engine.sheets import JobSetting, ScheduleRow


class FakeSheet:
    def __init__(self, rows):
        self._rows = rows
        self.appended = []

    def read_schedule(self):
        return list(self._rows)

    def append_schedule(self, when, industry, keyword, source, status="예정"):
        self.appended.append((when, industry, keyword, source, status))


class FakeResolver:
    def resolve(self, industry, manual, avoid, n):
        return [f"kw-{len(avoid)}"], "ai"


def job(industry, n=3, interval=3):
    return JobSetting(industry=industry, sites=["saramin"], campaign_id="1",
                      interval_days=interval, topup_count=n, pages="1-5", enabled=True)


def test_topup_fills_to_n(monkeypatch):
    sheet = FakeSheet([
        ScheduleRow(2, "2026-06-04", "물류", "3PL", "manual", "예정"),
    ])
    planner = SchedulePlanner(sheet, FakeResolver(), today=date(2026, 6, 1))
    planner.topup([job("물류", n=3)])
    # 기존 1개 예정 + 2개 생성 = 3
    assert len(sheet.appended) == 2
    # 간격 3일: 마지막 예정 06-04 → 06-07, 06-10
    whens = [a[0] for a in sheet.appended]
    assert whens == ["2026-06-07", "2026-06-10"]


def test_topup_skips_when_full():
    sheet = FakeSheet([
        ScheduleRow(2, "2026-06-04", "물류", "3PL", "ai", "예정"),
        ScheduleRow(3, "2026-06-07", "물류", "WMS", "ai", "예정"),
        ScheduleRow(4, "2026-06-10", "물류", "콜드체인", "ai", "예정"),
    ])
    planner = SchedulePlanner(sheet, FakeResolver(), today=date(2026, 6, 1))
    planner.topup([job("물류", n=3)])
    assert sheet.appended == []


def test_topup_avoid_uses_completed_and_pending():
    sheet = FakeSheet([
        ScheduleRow(2, "2026-06-01", "물류", "3PL", "ai", "✅완료"),
        ScheduleRow(3, "2026-06-04", "물류", "WMS", "ai", "예정"),
    ])
    captured = {}

    class CapResolver:
        def resolve(self, industry, manual, avoid, n):
            captured["avoid"] = list(avoid)
            return ["새키워드"], "ai"

    planner = SchedulePlanner(sheet, CapResolver(), today=date(2026, 6, 1))
    planner.topup([job("물류", n=2)])
    assert "3PL" in captured["avoid"] and "WMS" in captured["avoid"]
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/engine/test_planner.py -v` → FAIL.

- [ ] **Step 3: 구현**

Create `engine/planner.py`:

```python
"""예정표 top-up: 산업군별 미래 '예정' 행을 N개까지 미리 채운다."""
from datetime import date, datetime, timedelta


def _parse_date(s: str) -> date:
    s = (s or "").strip().split(" ")[0]
    return datetime.strptime(s, "%Y-%m-%d").date()


class SchedulePlanner:
    def __init__(self, sheet, resolver, today: date = None):
        self.sheet = sheet
        self.resolver = resolver
        self.today = today or date.today()

    def topup(self, settings: list):
        all_rows = self.sheet.read_schedule()
        for job in settings:
            rows = [r for r in all_rows if r.industry == job.industry]
            pending = [r for r in rows if r.status == "예정"]
            need = job.topup_count - len(pending)
            if need <= 0:
                continue

            avoid = [r.keyword for r in rows if r.keyword]
            # 마지막 예정일 기준(없으면 오늘)에서 간격을 더해 미래 날짜 생성
            future = [_parse_date(r.when) for r in pending] or [self.today]
            last = max(future)
            for _ in range(need):
                last = last + timedelta(days=job.interval_days)
                kws, source = self.resolver.resolve(
                    industry=job.industry, manual="", avoid=avoid, n=5)
                keyword = ", ".join(kws)
                self.sheet.append_schedule(
                    when=last.strftime("%Y-%m-%d"), industry=job.industry,
                    keyword=keyword, source=source, status="예정")
                if keyword:
                    avoid = avoid + kws  # 다음 생성에서 회피
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest tests/engine/test_planner.py -v` → PASS (3 passed).

- [ ] **Step 5: 커밋**

```bash
git add engine/planner.py tests/engine/test_planner.py
git commit -m "feat(engine): SchedulePlanner — 예정표 top-up(간격·회피·키워드 보존)"
```

---

## Task 5: AlertMonitor (delta 기반 bounce 경고 + suspend)

**규칙(스펙 §5,§6, 리스크 #8):** 캠페인 통계를 직전 snapshot과 비교해 **이번 구간 delta**로 판정. `Δsent ≥ MIN_BOUNCE_SAMPLE`일 때만 bounce율 계산. `≥critical`이면 suspend 플래그(`engine_state['suspended:<cid>']`), `≥warn`이면 경고. snapshot 갱신.

**Files:**
- Create: `engine/alerts.py`
- Test: `tests/engine/test_alerts.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/engine/test_alerts.py`:

```python
import json

from engine.alerts import AlertMonitor
from engine.models import EngineState


class FakeStats:
    def __init__(self, stats):
        self._stats = stats

    def get_campaign_stats(self, cid):
        return self._stats[cid]


class FakeSheet:
    def __init__(self):
        self.warnings = []

    def append_warning(self, run_id, kind, detail, value=""):
        self.warnings.append((kind, detail, value))


def monitor(session, stats_map, warn=0.05, critical=0.08, sample=50):
    return AlertMonitor(session, FakeStats(stats_map), FakeSheet(),
                        warn=warn, critical=critical, min_sample=sample)


def test_no_alert_below_sample(session):
    m = monitor(session, {"42": {"sent": 10, "bounced": 9}}, sample=50)
    m.poll_bounce("r1", ["42"])
    assert m.sheet.warnings == []  # 표본 미달 → 판정 안 함
    assert not m.suspended("42")


def test_warn_on_delta_rate(session):
    m = monitor(session, {"42": {"sent": 100, "bounced": 6}}, sample=50)
    m.poll_bounce("r1", ["42"])
    assert m.sheet.warnings[0][0] == "bounce_warn"
    assert not m.suspended("42")


def test_critical_suspends(session):
    m = monitor(session, {"42": {"sent": 100, "bounced": 9}}, sample=50)
    m.poll_bounce("r1", ["42"])
    assert m.sheet.warnings[0][0] == "bounce_critical"
    assert m.suspended("42")


def test_delta_uses_snapshot(session):
    session.add(EngineState(key="bounce_snapshot:42", value=json.dumps({"sent": 90, "bounced": 0})))
    session.commit()
    # 누적은 90/9이지만 이번 구간 delta는 10 sent / 9 bounced → 표본 미달
    m = monitor(session, {"42": {"sent": 100, "bounced": 9}}, sample=50)
    m.poll_bounce("r1", ["42"])
    assert m.sheet.warnings == []  # delta sent=10 < 50
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/engine/test_alerts.py -v` → FAIL.

- [ ] **Step 3: 구현**

Create `engine/alerts.py`:

```python
"""bounce율 경고: 직전 snapshot 대비 delta + 최소표본으로 판정(누적 오탐 방지)."""
import json

from engine.models import EngineState

SUSPEND_PREFIX = "suspended:"
SNAP_PREFIX = "bounce_snapshot:"


class AlertMonitor:
    def __init__(self, session, smartlead, sheet, warn=0.05, critical=0.08, min_sample=50):
        self.session = session
        self.smartlead = smartlead
        self.sheet = sheet
        self.warn = warn
        self.critical = critical
        self.min_sample = min_sample

    def _get(self, key):
        row = self.session.get(EngineState, key)
        return row.value if row else None

    def _set(self, key, value):
        row = self.session.get(EngineState, key)
        if row:
            row.value = value
        else:
            self.session.add(EngineState(key=key, value=value))
        self.session.commit()

    def suspended(self, campaign_id: str) -> bool:
        return self._get(SUSPEND_PREFIX + campaign_id) == "1"

    def _suspend(self, campaign_id: str):
        self._set(SUSPEND_PREFIX + campaign_id, "1")

    def poll_bounce(self, run_id: str, campaign_ids: list):
        for cid in campaign_ids:
            stats = self.smartlead.get_campaign_stats(cid)
            snap_raw = self._get(SNAP_PREFIX + cid)
            snap = json.loads(snap_raw) if snap_raw else {"sent": 0, "bounced": 0}
            d_sent = stats["sent"] - snap["sent"]
            d_bounced = stats["bounced"] - snap["bounced"]
            if d_sent >= self.min_sample:
                rate = d_bounced / d_sent if d_sent else 0.0
                pct = f"{rate*100:.1f}%"
                if rate >= self.critical:
                    self.sheet.append_warning(run_id, "bounce_critical", cid, pct)
                    self._suspend(cid)
                elif rate >= self.warn:
                    self.sheet.append_warning(run_id, "bounce_warn", cid, pct)
            self._set(SNAP_PREFIX + cid, json.dumps({"sent": stats["sent"], "bounced": stats["bounced"]}))
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest tests/engine/test_alerts.py -v` → PASS (4 passed).

- [ ] **Step 5: 커밋**

```bash
git add engine/alerts.py tests/engine/test_alerts.py
git commit -m "feat(engine): AlertMonitor — delta+최소표본 bounce 경고/suspend"
```

---

## Task 6: CrawlerService + RunPipeline (한 행 실행 조립)

**책임:** 스케줄 한 행을 받아 키워드 결정 → 크롤 → 검증 → dedup → (suspend면 보류) 푸시 → 발송내역 기록 → 상태 완료. CrawlerService는 사이트별 크롤러를 호출하고 `source`를 붙인다.

**Files:**
- Create: `engine/crawler_service.py`, `engine/pipeline.py`
- Test: `tests/engine/test_pipeline.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/engine/test_pipeline.py`:

```python
import asyncio

from engine.dedup import DedupStore
from engine.pipeline import RunPipeline
from engine.sheets import JobSetting, ScheduleRow
from engine.validator import EmailValidator


class FakeCrawlerService:
    async def crawl(self, sites, keywords, pages):
        return [{"company_name": "A", "emails": ["recruit@a.com"], "job_title": "t",
                 "company_url": "u", "homepage": "h", "source": "saramin"}]


class FakeSmartlead:
    def __init__(self):
        self.pushed = []

    def push_leads(self, campaign_id, records):
        from engine.smartlead import PushResult
        self.pushed.append((campaign_id, [r["email"] for r in records]))
        return PushResult(accepted=list(records), failed=[])


class FakeSheet:
    def __init__(self):
        self.history = []
        self.warnings = []
        self.status = []

    def append_history(self, **kw):
        self.history.append(kw)

    def append_warning(self, run_id, kind, detail, value=""):
        self.warnings.append(kind)

    def set_schedule_keyword(self, row_number, keyword, source):
        pass

    def set_schedule_status(self, row_number, status):
        self.status.append((row_number, status))


class FakeAlert:
    def suspended(self, cid):
        return False


def job():
    return JobSetting(industry="물류", sites=["saramin"], campaign_id="42",
                      interval_days=3, topup_count=5, pages="1-5", enabled=True)


def test_pipeline_pushes_and_records(session):
    row = ScheduleRow(2, "2026-06-04", "물류", "3PL", "manual", "예정")
    sheet, smart = FakeSheet(), FakeSmartlead()
    pipe = RunPipeline(
        session=session, crawler=FakeCrawlerService(),
        validator=EmailValidator(session, mx_lookup=lambda d: True),
        dedup=DedupStore(session), smartlead=smart, sheet=sheet,
        alert=FakeAlert(), min_pass_rate=0.4,
    )
    asyncio.run(pipe.run_row("r1", row, job()))
    assert smart.pushed == [("42", ["recruit@a.com"])]
    assert sheet.history[0]["push_status"] == "accepted"
    assert (2, "✅완료") in sheet.status


def test_pipeline_suspended_skips_push(session):
    row = ScheduleRow(2, "2026-06-04", "물류", "3PL", "manual", "예정")
    sheet, smart = FakeSheet(), FakeSmartlead()

    class Suspended:
        def suspended(self, cid):
            return True

    pipe = RunPipeline(
        session=session, crawler=FakeCrawlerService(),
        validator=EmailValidator(session, mx_lookup=lambda d: True),
        dedup=DedupStore(session), smartlead=smart, sheet=sheet,
        alert=Suspended(), min_pass_rate=0.4,
    )
    asyncio.run(pipe.run_row("r1", row, job()))
    assert smart.pushed == []  # 푸시 안 함
    assert sheet.history[0]["push_status"] == "suspended"
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/engine/test_pipeline.py -v` → FAIL.

- [ ] **Step 3: CrawlerService 구현**

Create `engine/crawler_service.py`:

```python
"""사이트별 크롤러 호출 + source 부착. crawlers 패키지만 의존(server.py 비의존)."""
from crawlers import SaraminCrawler, JobKoreaCrawler, WantedCrawler

CRAWLERS = {"saramin": SaraminCrawler, "jobkorea": JobKoreaCrawler, "wanted": WantedCrawler}


def _pages(spec: str):
    spec = (spec or "1-5").strip()
    if "-" in spec:
        a, b = spec.split("-", 1)
        return int(a), int(b)
    return int(spec), int(spec)


class CrawlerService:
    async def crawl(self, sites: list, keywords: list, pages: str) -> list:
        start, end = _pages(pages)
        companies = []
        for site in sites:
            cls = CRAWLERS.get(site)
            if not cls:
                continue
            async with cls() as crawler:
                for kw in keywords:
                    found = await crawler.crawl_with_emails(kw, start, end)
                    for c in found:
                        c["source"] = site
                    companies.extend(found)
        return companies
```

- [ ] **Step 4: RunPipeline 구현**

Create `engine/pipeline.py`:

```python
"""스케줄 한 행 실행: 크롤→검증→dedup→푸시(또는 보류)→발송내역→상태완료."""
from datetime import datetime


class RunPipeline:
    def __init__(self, session, crawler, validator, dedup, smartlead, sheet, alert, min_pass_rate=0.40):
        self.session = session
        self.crawler = crawler
        self.validator = validator
        self.dedup = dedup
        self.smartlead = smartlead
        self.sheet = sheet
        self.alert = alert
        self.min_pass_rate = min_pass_rate

    async def run_row(self, run_id, row, job):
        keywords = [k.strip() for k in row.keyword.split(",") if k.strip()]
        companies = await self.crawler.crawl(job.sites, keywords, job.pages)
        if not companies:
            self.sheet.append_warning(run_id, "crawl_zero", f"{job.industry}/{','.join(job.sites)}")

        result = self.validator.validate(companies)
        if result.pass_rate < self.min_pass_rate and (result.valid or result.dropped):
            self.sheet.append_warning(run_id, "low_pass_rate", job.industry, f"{result.pass_rate*100:.0f}%")

        fresh = self.dedup.filter_new(result.valid)

        if self.alert.suspended(job.campaign_id):
            self._record(run_id, row, job, fresh, "suspended", "")
        else:
            push = self.smartlead.push_leads(job.campaign_id, fresh)
            self.dedup.mark_pushed(push.accepted, job.campaign_id)
            accepted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._record(run_id, row, job, push.accepted, "accepted", accepted_at)
            self._record(run_id, row, job, push.failed, "failed", "")

        self.sheet.set_schedule_status(row.row_number, "✅완료")

    def _record(self, run_id, row, job, records, push_status, accepted_at):
        for r in records:
            self.sheet.append_history(
                run_id=run_id, company=r.get("company_name"), email=r["email"],
                industry=job.industry, keyword=row.keyword, site=r.get("source"),
                campaign_id=job.campaign_id,
                verdict=("role" if r.get("is_role") else "pass"),
                is_role=r.get("is_role", False),
                push_status=push_status, accepted_at=accepted_at, note="",
            )
```

- [ ] **Step 5: 통과 확인** — `.venv/bin/pytest tests/engine/test_pipeline.py -v` → PASS (2 passed).

- [ ] **Step 6: 커밋**

```bash
git add engine/crawler_service.py engine/pipeline.py tests/engine/test_pipeline.py
git commit -m "feat(engine): CrawlerService + RunPipeline (행 실행 조립, suspend 보류)"
```

---

## Task 7: HourlyTick 스케줄러 + 서버 통합 + 배포

**책임:** 매시간 도래행을 찾아 `run_lock`으로 직렬화하며 RunPipeline 실행, 그 전에 SchedulePlanner.topup, 그 후 AlertMonitor.poll. server.py 시작 시 APScheduler 등록 + `/healthz`.

**Files:**
- Create: `engine/scheduler.py`
- Modify: `server.py` (startup 등록 + `/healthz`)
- Test: `tests/engine/test_scheduler.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/engine/test_scheduler.py`:

```python
import asyncio
from datetime import datetime

from engine.scheduler import due_rows, acquire_lock, release_lock, clear_stale_locks
from engine.models import RunLock
from engine.sheets import ScheduleRow


def row(rn, when, status="예정"):
    return ScheduleRow(rn, when, "물류", "3PL", "ai", status)


def test_due_rows_filters_by_time_and_status():
    now = datetime(2026, 6, 4, 10, 0)
    rows = [
        row(2, "2026-06-04 09:00", "예정"),     # 도래 → 포함
        row(3, "2026-06-05 09:00", "예정"),     # 미래 → 제외
        row(4, "2026-06-01 09:00", "✅완료"),   # 완료 → 제외
        row(5, "2026-06-04", "예정"),           # 날짜만 → 09:00로 파싱 → 도래
    ]
    due = due_rows(rows, now)
    assert [r.row_number for r in due] == [2, 5]


def test_lock_acquire_and_release(session):
    assert acquire_lock(session, "물류|2026-06-04 09:00") is True
    assert acquire_lock(session, "물류|2026-06-04 09:00") is False  # 이미 잠김
    release_lock(session, "물류|2026-06-04 09:00")
    assert acquire_lock(session, "물류|2026-06-04 09:00") is True


def test_clear_stale_locks(session):
    session.add(RunLock(row_key="old", locked_at=datetime(2020, 1, 1)))
    session.commit()
    clear_stale_locks(session, before=datetime(2026, 1, 1))
    assert session.get(RunLock, "old") is None
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/pytest tests/engine/test_scheduler.py -v` → FAIL.

- [ ] **Step 3: scheduler.py 구현**

Create `engine/scheduler.py`:

```python
"""HourlyTick: 도래행 판정 + run_lock 직렬화 + APScheduler 등록."""
from datetime import datetime

from engine.models import RunLock


def _parse_when(when: str) -> datetime:
    when = (when or "").strip()
    try:
        return datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.strptime(when.split(" ")[0], "%Y-%m-%d").replace(hour=9, minute=0)


def due_rows(rows: list, now: datetime) -> list:
    out = []
    for r in rows:
        if r.status != "예정":
            continue
        try:
            when = _parse_when(r.when)
        except ValueError:
            continue
        if when <= now:
            out.append(r)
    return out


def lock_key(row) -> str:
    return f"{row.industry}|{row.when}"


def acquire_lock(session, key: str) -> bool:
    if session.get(RunLock, key):
        return False
    session.add(RunLock(row_key=key, locked_at=datetime.utcnow()))
    session.commit()
    return True


def release_lock(session, key: str):
    row = session.get(RunLock, key)
    if row:
        session.delete(row)
        session.commit()


def clear_stale_locks(session, before: datetime):
    for lock in session.query(RunLock).filter(RunLock.locked_at < before).all():
        session.delete(lock)
    session.commit()
```

- [ ] **Step 4: 통과 확인** — `.venv/bin/pytest tests/engine/test_scheduler.py -v` → PASS (3 passed).

- [ ] **Step 5: 서버 통합 (수동 검증)**

`server.py`에 startup 훅과 헬스 라우트를 추가한다. 기존 import 블록 아래, `app = FastAPI(...)` 생성 이후에 추가:

```python
# --- 자동화 엔진 (시트 기반 콜드메일) ---
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from engine.db import Base, engine as state_engine, SessionLocal as StateSession
import engine.models  # noqa: F401
from engine.scheduler import due_rows, lock_key, acquire_lock, release_lock, clear_stale_locks
# (RunPipeline 등 조립은 _run_tick에서 구성)

_engine_scheduler = None


@app.on_event("startup")
async def _start_engine():
    global _engine_scheduler
    if os.getenv("ENGINE_ENABLED", "1") != "1":
        return
    Base.metadata.create_all(state_engine)
    with StateSession() as s:
        from datetime import datetime, timedelta
        clear_stale_locks(s, before=datetime.utcnow() - timedelta(hours=6))
    _engine_scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    _engine_scheduler.add_job(_run_tick, "interval", hours=1,
                              max_instances=1, coalesce=True, id="hourly_tick")
    _engine_scheduler.start()


@app.get("/healthz")
async def healthz():
    ok = True
    try:
        with StateSession() as s:
            s.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        ok = False
    return {"ok": ok}
```

그리고 `_run_tick` 코루틴(동일 파일 하단)에서 컴포넌트를 조립한다. 이 함수는 통합 지점이므로 **구현 후 실연동 스모크 테스트로 검증**한다:

```python
async def _run_tick():
    from datetime import datetime
    from engine.settings import get_engine_settings
    from engine.sheets import SheetControl, open_control_sheet
    from engine.gemini import GeminiClient
    from engine.keywords import KeywordResolver
    from engine.planner import SchedulePlanner
    from engine.smartlead import SmartleadClient
    from engine.alerts import AlertMonitor
    from engine.crawler_service import CrawlerService
    from engine.validator import EmailValidator
    from engine.dedup import DedupStore
    from engine.pipeline import RunPipeline

    cfg = get_engine_settings()
    ss = open_control_sheet(cfg.google_credentials_json, cfg.control_sheet_url)
    sheet = SheetControl(ss)
    gemini = GeminiClient(api_key=cfg.gemini_api_key)
    resolver = KeywordResolver(gemini=gemini)
    smartlead = SmartleadClient(api_key=cfg.smartlead_api_key)

    settings = sheet.read_settings()
    SchedulePlanner(sheet, resolver).topup(settings)

    by_industry = {j.industry: j for j in settings}
    now = datetime.now()
    rows = sheet.read_schedule()
    for row in due_rows(rows, now):
        job = by_industry.get(row.industry)
        if not job:
            continue
        key = lock_key(row)
        with StateSession() as s:
            if not acquire_lock(s, key):
                continue
        try:
            with StateSession() as s:
                # 키워드 비면 채워서 시트에 기록
                if not row.keyword:
                    kws, src = resolver.resolve(job.industry, "", avoid=[], n=job.topup_count)
                    sheet.set_schedule_keyword(row.row_number, ", ".join(kws), src)
                    row.keyword = ", ".join(kws)
                alert = AlertMonitor(s, smartlead, sheet,
                                     warn=cfg.bounce_warn, critical=cfg.bounce_critical,
                                     min_sample=cfg.min_bounce_sample)
                pipe = RunPipeline(
                    session=s, crawler=CrawlerService(),
                    validator=EmailValidator(s), dedup=DedupStore(s),
                    smartlead=smartlead, sheet=sheet, alert=alert,
                    min_pass_rate=cfg.min_pass_rate)
                await pipe.run_row(run_id=now.strftime("%Y%m%d%H%M"), row=row, job=job)
        finally:
            with StateSession() as s:
                release_lock(s, key)

    with StateSession() as s:
        alert = AlertMonitor(s, smartlead, sheet,
                             warn=cfg.bounce_warn, critical=cfg.bounce_critical,
                             min_sample=cfg.min_bounce_sample)
        campaigns = list({j.campaign_id for j in settings})
        alert.poll_bounce(run_id=now.strftime("%Y%m%d%H%M"), campaign_ids=campaigns)
```

수동 검증:
- Run: `.venv/bin/python -c "import server"` → import 에러 없음 (apscheduler/engine import 정상).
- Run: 전체 테스트 `.venv/bin/pytest -q` → 기존 + 신규 전부 통과.

- [ ] **Step 6: 배포 설정**

`requirements.txt`에 (Task 2에서 추가 안 했다면) `apscheduler==3.10.4`, `google-genai==0.3.0` 포함 확인.

`docs/`에 컨트롤 시트 템플릿 안내를 README 또는 `docs/control-sheet-template.md`로 작성:
- 시트 4개 탭(`⚙️설정`/`📅키워드스케줄`/`발송내역`/`⚠️경고`)과 헤더(본 문서 상단 "시트 헤더") 그대로 생성.
- 봇 서비스계정 이메일을 시트에 편집자로 공유.

Railway:
- 환경변수: `SMARTLEAD_API_KEY`, `GEMINI_API_KEY`, `CONTROL_SHEET_URL`, `STATE_DB_URL=sqlite:////data/state.db`, (재사용)`GOOGLE_CREDENTIALS_JSON`. 임계치는 기본값 사용.
- `/data` 볼륨 추가(상태 DB).

- [ ] **Step 7: 커밋**

```bash
git add engine/scheduler.py server.py requirements.txt docs/control-sheet-template.md
git commit -m "feat(engine): HourlyTick 스케줄러 + server 통합 + 배포 설정"
```

---

## Plan 2 완료 기준

- [ ] `.venv/bin/pytest -q` 전체(Plan 1 + Plan 2) 통과
- [ ] `python -c "import server"` 성공 (OAuth env 유무와 무관하게 engine import 정상)
- [ ] `engine/` 어떤 모듈도 `server.py`/`app/`을 import 하지 않음
- [ ] 컨트롤 시트 템플릿 문서 존재
- [ ] (실연동 스모크) 테스트 캠페인으로 `⚙️설정` 1행 → 수동 tick 1회 → `발송내역`에 accepted 기록 + dedup 동작 확인

## 통합 시 확정해야 할 외부 스펙 (구현 중 실응답으로 검증)
- Smartlead `analytics` 응답의 정확한 필드명(`sent_count`/`bounce_count`).
- Smartlead add-leads 응답에서 중복/실패 카운트 → push_status 세분화 여부.
- google-genai 설치 버전·`generate_content` 응답 형태(`resp.text`).
- APScheduler 버전 호환(이벤트 루프) — Railway 단일 replica 가정.
</content>
