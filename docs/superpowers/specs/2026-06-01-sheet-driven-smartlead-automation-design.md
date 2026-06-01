# 시트 기반 콜드메일 자동화 디자인 (산업군 → 키워드 → 크롤 → 검증 → Smartlead 푸시)

**작성일**: 2026-06-01
**대상 코드베이스**: `/Users/uhuru/dev/emailmak-main` (Email Crawler)
**상태**: 초안 — 사용자 리뷰 대기
**선행 문서**: `2026-05-11-multi-user-crawl-validate-smartlead-design.md` (멀티유저 풀버전). 본 문서는 그중 **단일 사용자 · 시트 주도** 슬라이스만 다룬다.

---

## 1. 배경과 목표

### 현재 상태
- FastAPI 단일 컨테이너로 운영되는 채용 사이트(사람인/잡코리아/원티드) 이메일 크롤러.
- 결과는 CSV 다운로드 또는 단일 공용 Google Sheets로 내보내기 (수동).
- Railway 배포: `kitt.ai.ceo@gmail.com` 계정 / 프로젝트 `capable-harmony` / `web-production-ff6a3.up.railway.app` / GitHub `chegom/emailmak` 자동배포.

### 해결하려는 문제
1. 수집 → (검증) → Smartlead 캠페인 리드 업로드를 **매번 수동**으로 한다.
2. 콜드메일 **바운스**를 줄이고 싶다.
3. 한 키워드를 오래 돌리면 **중복 이메일**이 쌓인다 → 키워드를 며칠마다 바꿔야 한다.
4. 관리 UI를 따로 만들고 쓰는 건 번거롭다 → **구글 시트 한 장에서 다 관리**하고 싶다 (주기·키워드·캠페인 전부).
5. **앞으로 어떤 키워드로 나갈지 미리 보고**, 필요하면 중간에 바꾸고 싶다.

### 목표
- 산업군 → 키워드 → 크롤 → 검증 → Smartlead 캠페인 리드 투입 → 시트에 내역 누적, **무인 자동**.
- **모든 노브를 시트에서**: 주기, 키워드, 산업군, 사이트, 캠페인, on/off. 시트를 고치면 다음 실행부터 반영.
- **키워드 예정표(미리보기)**: 앞으로 N회분 키워드를 AI가 미리 생성해 시트에 채워둔다. 사용자가 예정 행을 고치면 그게 나간다.
- **키워드 하이브리드**: 예정 행에 사람이 적으면 그걸, 비어 있으면 Gemini가 채움 (최근 사용 회피 → 중복↓).
- **사전 검증**으로 바운스 감소: MX + 문법 + 시스템주소/일회용 도메인 제외 (Railway 포트25 차단 환경에서 가능한 범위).
- **사후 경고**: Smartlead 통계를 폴링해 bounce율/이슈가 임계치를 넘으면 시트 `⚠️경고` 탭에 기록.

### 비목표 (Out of Scope)
- 멀티유저 / Google OAuth / 사용자별 격리.
- SMTP `RCPT TO` 실사서함 검증 (Railway 아웃바운드 25번 포트 차단으로 불가).
- 캐치올(catch-all) 도메인 정밀 감지.
- 블랙리스트(개인/팀), 바운스 웹훅 수신.
- 콜드메일 본문 AI 생성, 캠페인 성과(오픈/클릭/답장) 대시보드.
- **웹 관리 대시보드/관리자 화면 — 향후 별도 작업**(1차는 시트가 곧 대시보드).

---

## 2. 핵심 결정 요약

| 영역 | 결정 |
|------|------|
| 범위 | 단일 사용자 · 시트 주도 · 무화면 엔진 |
| 트리거 | 엔진이 **매시간 깨어나** `📅키워드스케줄`에서 **예정일 도래분**을 실행 |
| 주기 설정 | `⚙️설정`의 `주기(일)` 값(기본 3) — AI가 예정표 간격을 이 값으로 잡음. 개별 날짜는 시트에서 직접 조정 가능 |
| 키워드 예정표 | AI가 앞으로 **N회분 미리 생성**해 `📅키워드스케줄`에 채움. 줄어들면 자동 top-up |
| 키워드 | 하이브리드 — 예정 행 수동 입력 우선, 비면 **Gemini 2.5 Flash** 자동 생성(최근 사용 회피) |
| 검증 | **MX + 문법 + 시스템주소/일회용 제외** (역할주소는 포함) |
| 역할주소 정책 | `recruit@ hr@ info@ sales@ contact@` 등 업무용 역할주소 **포함**(주 타깃), `no-reply@ postmaster@ mailer-daemon@ noreply@ donotreply@` 등 시스템주소만 제외. 시트에 역할주소 여부 표시 |
| 중복 제거 | `발송내역`의 **`push_status=accepted` 행만** 기준 + 로컬 캐시. 수집됐으나 미푸시(suspended/failed/skipped)는 dedup에서 **제외** → 다음 실행 재시도 가능 |
| Smartlead 푸시 | 캠페인에 리드 배치 투입(요청당 최대 100). 옵션은 공식 파라미터명으로 명시(§9) |
| 경고 방식 | **폴링** — 매 실행 시 Smartlead 캠페인 통계 조회 (공개 웹훅 불필요) |
| 임계치 | **이번 구간(delta·최소표본)** bounce율 ≥5% ⚠️경고 / ≥8% 🚨심각(자동 푸시 중단). 검증 통과율 <40% ⚠️. 크롤 0건 ⚠️ |
| 컨트롤 패널 | Google Sheets 1장 (`⚙️설정` / `📅키워드스케줄` / `발송내역` / `⚠️경고` 탭) |
| 상태 저장 | 경량 SQLite(Railway 볼륨) — dedup 캐시 + 엔진 상태 + 실행 락. 시트가 사람용 source, DB는 엔진 내부용 |
| 동시실행 방지 | APScheduler `max_instances=1, coalesce=True` + 행 상태 `예정→running→완료` 전이(SQLite `run_lock`) |
| 엔진 설정 | `app/config`(OAuth 필수)와 **분리한 `EngineSettings`** — OAuth env 없이 부팅 |
| 시크릿 | `SMARTLEAD_API_KEY`, `GEMINI_API_KEY` 환경변수. `GOOGLE_CREDENTIALS_JSON` 재사용 |

---

## 3. 아키텍처

```
┌───────────────────────── Google Sheet (컨트롤 패널 = DB) ─────────────────────────┐
│  ⚙️설정     (사람 입력) : 산업군, 사이트, 캠페인ID, 주기(일), 미리채울회수N, 활성화 │
│  📅키워드스케줄 (양방향): 예정일, 산업군, 키워드, 출처(ai/manual), 상태(예정/완료) │
│                          └ AI가 앞으로 N회분 미리 채움. 사람이 고치면 manual로 나감 │
│  발송내역    (엔진 기록): 기록일시, 회사, 이메일, …, 검증결과, 역할주소여부,         │
│                          push_status(accepted/skipped/failed/suspended) ← dedup=accepted│
│  ⚠️경고      (엔진 기록): 일시, 종류, 상세, 수치                                    │
└───────────────────────────────────────────────────────────────────────────────────┘
        ▲ 읽기(⚙️설정·📅스케줄·발송내역)          │ 쓰기(📅스케줄 채움/상태, 발송내역, ⚠️경고)
        │                                          ▼
┌──────────────────────── FastAPI App (Railway, 무화면 엔진) ────────────────────────┐
│  HourlyTick (APScheduler, interval=1h, Asia/Seoul)                                  │
│    ├─ SchedulePlanner.topup()      예정표가 N회분 미만이면 AI로 뒤를 채움           │
│    └─ for each 도래행(예정일≤now, 상태=예정) in 📅키워드스케줄:                      │
│         RunPipeline.execute(row):                                                   │
│           1) SheetControl.read_settings()      ⚙️설정에서 사이트/캠페인/페이지 매칭 │
│           2) KeywordResolver.resolve(row)      키워드 있으면 그대로 / 비면 Gemini   │
│           3) CrawlerService.crawl()            기존 saramin/jobkorea/wanted 재사용  │
│           4) EmailValidator.validate()         MX + 문법 + 시스템/일회용 제외        │
│           5) DedupStore.filter_new()           발송내역 + 로컬 캐시 대조            │
│           6) SmartleadClient.push_leads()      배치 100, ignore_duplicate ON        │
│           7) SheetRecorder.append() / 상태=✅완료                                   │
│           8) AlertMonitor.check()              Smartlead 통계 폴링 → ⚠️경고 판정    │
│                                                                                    │
│  외부:  Gemini API (키워드)   |   Smartlead API (리드/통계)   |   기존 봇 시트계정  │
│  상태:  SQLite(/data/state.db) — pushed_email(accepted), mx 캐시, run_lock, snapshot│
└────────────────────────────────────────────────────────────────────────────────────┘
```

### 컴포넌트 책임 경계
- **SheetControl**: 시트 ↔ 파이썬 구조체 변환. `⚙️설정`/`📅키워드스케줄` 읽기·검증, 각 탭 append·상태 갱신. gspread 래퍼(`utils/google_sheets.py`의 `GoogleSheetExporter` 확장/재사용).
- **SchedulePlanner**: `📅키워드스케줄`이 N회분 미만이면 미래 행을 생성. 날짜는 `주기(일)` 간격, 키워드는 Gemini가 산업군별로(최근 사용 회피). 이미 있는 manual 행은 보존.
- **KeywordResolver**: 실행 행의 키워드 결정 — manual 있으면 그대로, 없으면 GeminiClient(산업군 + 회피목록).
- **GeminiClient**: 산업군 + 회피목록 → 키워드 N개. 모델 `gemini-2.5-flash`. 실패 시 빈 결과 → ⚠️경고 + 해당 행 보류.
- **CrawlerService**: 크롤러 통합 어댑터. ⚠️ **선행 수정 필요** — `WantedCrawler`에 `crawl_with_emails()`가 없어 wanted 선택 시 크래시(server.py:108 `crawl_with_emails` 가정 vs crawlers/wanted.py는 `search`/`get_company_detail`/`fetch_json`만 보유; saramin·jobkorea엔 존재). `search → get_company_detail → extract_emails` 공통 어댑터로 묶거나 `WantedCrawler.crawl_with_emails()`를 추가해 시그니처를 통일한다.
- **EmailValidator**: 도메인 MX 조회(dnspython, 7일 캐시) + 문법 + 시스템주소/일회용 도메인 제외. **SMTP 핸드셰이크 안 함.**
- **DedupStore**: `발송내역` 이메일 집합 + 로컬 SQLite 캐시로 이미 푸시된 주소 제외.
- **SmartleadClient**: `POST /api/v1/campaigns/{id}/leads`(배치) + 통계 조회. 4xx/401/429/5xx 분기.
- **SheetRecorder**: 결과를 `발송내역`에 append, 실행 행 `상태=✅완료`, 경고를 `⚠️경고`에 append.
- **AlertMonitor**: 사전 지표(크롤0/통과율) + 폴링 지표(bounce율)로 임계치 판정 → 경고 + 필요 시 자동 푸시 중단 플래그.
- **HourlyTick/RunPipeline**: 매시간 도래행을 찾아 서비스들을 순서대로 조립 실행.

각 컴포넌트는 인터페이스가 명확하고 독립 테스트 가능. 현재 단일 `server.py` 로직을 `services/` 모듈로 분리하는 작업이 포함된다(작업 중 코드 정돈 차원).

---

## 4. 데이터 모델

### 4.1 Google Sheet 탭 스키마 (컨트롤 시트, `CONTROL_SHEET_URL`)

**`⚙️설정`** — 사람이 입력. 한 행 = 한 산업군 작업.

| 열 | 예시 | 설명 |
|----|------|------|
| 산업군 | `물류` | 키워드 생성·매칭 키 |
| 사이트 | `saramin` | saramin / jobkorea / wanted (콤마로 복수 가능) |
| 캠페인ID | `123456` | Smartlead 캠페인. 거의 고정 |
| 주기(일) | `3` | 예정표 간격. AI가 이 간격으로 미래 행 생성 |
| 미리채울회수 | `5` | 항상 미리 보여줄 예정 행 수(N) |
| 페이지 | `1-5` | (선택) 크롤 페이지 범위, 기본 1-5 |
| 활성화 | `Y` | Y/N. N이면 해당 산업군 예정표 진행/생성 중단 |

**`📅키워드스케줄`** — 양방향(엔진 생성 + 사람 편집). **미리보기 + 트리거 원천.**

| 열 | 예시 | 설명 |
|----|------|------|
| 예정일시 | `2026-06-04 09:00` | 도래 시 실행. **날짜만 입력하면 Asia/Seoul 09:00로 파싱** |
| 산업군 | `물류` | `⚙️설정` 행과 매칭 |
| 키워드 | `3PL, 풀필먼트` | 비우면 실행/top-up 시 AI가 채움. 적혀 있으면 그대로 사용 |
| 출처 | `ai` / `manual` | **표시용일 뿐.** 보호 기준 아님 |
| 상태 | `예정` / `running` / `✅완료` / `보류` | 엔진이 갱신. `running`=처리중(락), `보류`=AI/크롤 실패 |

- **키워드 보호 규칙(개정)**: **키워드 칸이 비어 있지 않으면 엔진은 절대 덮어쓰지 않는다.** 사람이 `출처`를 안 바꿔도 안전(출처는 표시용). 엔진은 `키워드`가 빈 `예정` 행만 채우고 그때 `출처=ai`로 표시.
- `완료` 행이 곧 **사용 키워드 이력** → 별도 이력 탭 불필요. SchedulePlanner는 이 이력을 회피목록으로 사용.

**`발송내역`** — 엔진 기록(append). 열: `기록일시, 실행ID, 회사명, 이메일, 산업군, 키워드, 사이트, 캠페인ID, 검증결과(pass/role), 역할주소여부, push_status, accepted_at, smartlead_응답요약`.
- `push_status` ∈ `accepted` / `skipped`(이미 dedup됨) / `failed`(API오류) / `suspended`(회로차단으로 미푸시).
- **dedup은 `push_status=accepted` 행만 기준** — 미푸시 이메일이 "발송됨"으로 오인되지 않음.
- (선택) 수집내역과 발송내역을 굳이 더 나누지 않고, `push_status`로 한 탭에서 구분.

**`⚠️경고`** — 엔진 기록(append). 열: `일시, 실행ID, 종류, 상세, 수치`.
- 종류: `crawl_zero` / `low_pass_rate` / `bounce_warn` / `bounce_critical` / `api_error` / `settings_invalid`.

### 4.2 로컬 상태 (SQLite, `/data/state.db`, Railway 볼륨)
엔진 내부용. 시트가 사람용 source of truth지만, 매 실행마다 시트를 풀스캔하면 느리고 API 쿼터를 먹으므로 캐시만 로컬 보관.

```sql
CREATE TABLE engine_state (
  key   TEXT PRIMARY KEY,            -- 'suspended:<cid>', 'bounce_snapshot:<cid>'(JSON {sent,bounced})
  value TEXT
);

CREATE TABLE pushed_emails (
  email        TEXT PRIMARY KEY,      -- 정규화(소문자) 이메일. accepted만 적재
  domain       TEXT,
  campaign_id  TEXT,
  pushed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_pushed_domain ON pushed_emails(domain);

CREATE TABLE mx_cache (
  domain     TEXT PRIMARY KEY,
  mx_valid   BOOLEAN,
  checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP   -- TTL 7일
);

CREATE TABLE run_lock (
  row_key    TEXT PRIMARY KEY,        -- 📅스케줄 행 식별(산업군 + 예정일시)
  locked_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- 부팅 시 `pushed_emails`가 비어 있으면(볼륨 초기화 등) `발송내역`의 **`push_status=accepted` 행만** 1회 backfill.
- **스케줄 상태(다음 실행 시점)는 시트 `📅키워드스케줄`이 source** — 재시작에도 시트만 보면 됨.
- 부팅 시 오래된 `run_lock`·`상태=running` 행은 정리(고아 락 해제) 후 시작.
- bounce 판단은 누적이 아니라 `bounce_snapshot`과의 **delta**로(§5) — 과거 누적 바운스로 인한 오탐 방지.

### 4.3 시크릿 보호
- `SMARTLEAD_API_KEY`, `GEMINI_API_KEY`는 환경변수에서만 읽고 로그에 마스킹(`sk-***...xyz`).
- 시트에는 API 키를 저장하지 않는다 (시트는 공유 위험).

---

## 5. 데이터 흐름 — 매시간 tick

```
HourlyTick():                                    # APScheduler interval=1h, Asia/Seoul
  1. settings = SheetControl.read_settings()      # ⚙️설정 활성(Y) 산업군들
       - 행 검증 실패 → ⚠️경고(settings_invalid), 해당 산업군 skip
  2. SchedulePlanner.topup(settings):             # 예정표 미리 채우기
       for each 활성 산업군:
         미래 '예정' 행 수 < 미리채울회수(N) 이면:
           마지막 예정일 + 주기(일) 간격으로 부족분 행 생성
           각 행 키워드 = Gemini(산업군, 회피목록=완료이력+기존예정) ; 출처=ai
       (manual 행·기존 예정 행은 건드리지 않음)
  3. due = 📅키워드스케줄 중 (예정일시 ≤ now AND 상태=예정)   # 날짜만이면 09:00(Asia/Seoul)
  4. for each row in due:
       0) run_lock 획득(있으면 다른 워커가 처리중 → skip). 행 상태 예정→running
       a. keywords = KeywordResolver.resolve(row)         # 키워드 칸 있으면 그대로, 비면 Gemini
            실패 → 상태=보류 + ⚠️경고(api_error), 락 해제, continue
            (ai로 채웠으면 그 키워드를 시트 row에 기록, 출처=ai)
       b. job = settings[row.산업군]                       # 사이트/캠페인/페이지
       c. companies = CrawlerService.crawl(job.사이트, keywords, job.페이지)
            0건 → ⚠️경고(crawl_zero)
       d. (valid, dropped) = EmailValidator.validate(companies)
            통과율 < MIN_PASS_RATE → ⚠️경고(low_pass_rate)
       e. fresh = DedupStore.filter_new(valid)             # accepted 이력만 제외 기준
       f. if AlertMonitor.suspended(job.캠페인ID):        # 직전 bounce_critical
            발송내역에 push_status=suspended로 기록(=미푸시, dedup 제외), ⚠️경고("푸시 보류")
          else:
            result = SmartleadClient.push_leads(job.캠페인ID, fresh)   # 배치 100
            DedupStore.mark_pushed(result.accepted)        # accepted만 등록
            # 미수락분은 push_status=failed/skipped → dedup 안 됨 → 다음 실행 재시도
       g. SheetRecorder.append_history(row, valid, result) # 행별 push_status 기록
          row.상태 = ✅완료, run_lock 해제
  5. AlertMonitor.poll_bounce(active_campaigns):     # 캠페인별 통계 — delta 기준
       snap = engine_state['bounce_snapshot:<cid>']  # 직전 {sent,bounced}
       Δsent = sent - snap.sent ; Δbounced = bounced - snap.bounced
       if Δsent ≥ MIN_BOUNCE_SAMPLE:                 # 최소 표본 충족 시에만 판정
         rate = Δbounced / Δsent
         rate ≥ BOUNCE_CRITICAL → ⚠️경고(bounce_critical) + suspend(campaign)
         rate ≥ BOUNCE_WARN     → ⚠️경고(bounce_warn)
       engine_state['bounce_snapshot:<cid>'] = {sent,bounced}
```

### 멱등성·재실행 안전성
- **푸시 성공분만 `pushed_emails`/`발송내역`에 적재** → 중간 실패 시 다음 tick에서 미푸시분만 재시도.
- 행 상태는 `완료`로만 전이되므로 **같은 예정 행이 두 번 실행되지 않음**(tick 도중 죽으면 `예정`으로 남아 다음 tick 재수행, 중복은 dedup이 흡수).
- 크롤은 멱등 아님이나 dedup으로 같은 이메일 재푸시 없음. Smartlead `ignore_duplicate`로 서버측 2중 방어.
- 컨테이너 재시작: 스케줄 상태가 시트에 있으므로 다음 tick에 자연 복구.

---

## 6. 안전장치 (무인 자동화 가드레일)

| # | 안전장치 | 위치 | 효과 |
|---|---------|------|------|
| 1 | bounce 회로차단(delta) | AlertMonitor.poll_bounce | **이번 구간**(최소 표본 `MIN_BOUNCE_SAMPLE` 이상) bounce율 ≥8%면 캠페인 자동 푸시 중단 + 🚨경고. 과거 누적값 오탐 방지 |
| 2 | 검증 통과율 가드 | EmailValidator 후 | <40%면 ⚠️경고 (키워드/사이트 품질 의심) |
| 3 | 크롤 0건 감지 | CrawlerService 후 | 사이트 구조 변경/키워드 부적합 의심 → ⚠️경고 |
| 4 | 시스템주소·일회용 제외 | EmailValidator | 무인 모드 강제 ON |
| 5 | dedup 2중화 | DedupStore + Smartlead 옵션 | 동일 이메일 재발송 방지 |
| 6 | 설정 검증 | SheetControl | 잘못된 사이트/캠페인/페이지/주기 → 행 skip + ⚠️경고 |
| 7 | 일일 푸시 상한(선택) | SmartleadClient | `SMARTLEAD_DAILY_LIMIT` 초과분 다음 tick 이월 |
| 8 | 키워드 보호 | SchedulePlanner | **키워드 칸이 비어있지 않으면** 엔진이 절대 덮어쓰지 않음(출처 무관) |
| 9 | 동시실행 락 | APScheduler + run_lock | `max_instances=1, coalesce=True` + 행 `running` 전이로 같은 due 행 중복 처리 방지 |
| 10 | dedup 정확성 | DedupStore | `push_status=accepted`만 dedup 기준 → 미푸시 이메일 영구 제외 사고 방지 |

> bounce_critical로 자동 중단된 캠페인 재개: `⚠️경고`를 보고 원인 처리 후 **재개 방법은 구현 계획에서 확정**(후보: `⚙️설정`에 재개 표시 / 쿨다운 자동 해제).

---

## 7. 에러 처리

| 단계 | 에러 | 처리 |
|------|------|------|
| 시트 읽기 | 권한/시트 없음 | 실행 실패 로그, 재시도. (사람 개입 필요) |
| 설정 파싱 | 잘못된 값 | 해당 행 skip + ⚠️경고(settings_invalid) |
| Gemini | 타임아웃/4xx/쿼터 | 행 상태=보류 + ⚠️경고(api_error). manual 키워드면 영향 없음 |
| 크롤 | 네트워크/5xx | 회사당 최대 3회 지수 백오프, 실패분 skip |
| 크롤 | 403/429 봇차단 | 30초 백오프 1회 재시도, 재실패 시 해당 사이트 skip |
| MX 조회 | DNS 실패 | mx_valid=false 캐싱(7일), 해당 도메인 제외 |
| Smartlead | 4xx | 즉시 중단, 응답 본문 ⚠️경고 기록 |
| Smartlead | 401 | 푸시 중단 + ⚠️경고("키 확인") |
| Smartlead | 429 | 60초 백오프 최대 5회, 남은 건 다음 tick 이월 |
| Smartlead | 5xx | 3회 지수 백오프 후 이월 |
| 시트 쓰기 | rate limit | 백오프 후 재시도 (단일 사용자라 경합 적음) |
| DB | 락 | SQLite WAL + busy_timeout=5s |
| DB | 볼륨 장애 | `/healthz` 실패 → Railway 재시작, pushed_emails는 시트에서 backfill |

---

## 8. 관측성
- **시트 `⚠️경고` 탭** — 사람이 보는 1차 알림.
- **시트 `📅키워드스케줄`(완료)·`발송내역`** — 매 실행의 처리 결과/이력.
- **구조화 stdout 로그(JSON)** — Railway 콘솔 검색용, 시크릿 마스킹.
- **`GET /healthz`** — DB ping + 시트 접근 가능 여부 + 마지막 tick 시각 노출.
- (선택) 다음 단계에서 이메일 알림 추가 가능 — 1차는 시트 경고로 충분.

---

## 9. 배포

### 환경변수 (신규)
```
SMARTLEAD_API_KEY            # Smartlead 리드/통계 API
GEMINI_API_KEY              # 키워드 생성 (Gemini 2.5 Flash)
CONTROL_SHEET_URL          # 컨트롤 패널 시트 URL
# 임계치 (기본값 있음, 선택) — 주기/N은 시트(⚙️설정)에서 관리
BOUNCE_WARN=0.05
BOUNCE_CRITICAL=0.08
MIN_BOUNCE_SAMPLE=50        # delta 판정 최소 표본
MIN_PASS_RATE=0.40
SMARTLEAD_DAILY_LIMIT=200
# 기존 재사용
GOOGLE_CREDENTIALS_JSON     # 시트 읽기/쓰기 (봇 서비스계정)
```
> 보안: 기존에 노출됐던 서비스계정 키(`crawler-bot@emailmarketing-485502`)는 폐기·재발급 권장(이전 작업의 후속).

### 엔진 설정 분리 (OAuth 비의존)
`app/config.py`는 `app_secret_key`·`google_oauth_client_id`·`google_oauth_client_secret`를 **필수**로 요구하고, `app/db.py`는 import 시 `get_settings()`를 호출한다(app/db.py:12,25). 이 엔진은 OAuth가 비목표이므로 그대로 쓰면 **OAuth env 없이는 부팅이 죽는다.** 따라서:
- 엔진 전용 **`EngineSettings`**(필수: `SMARTLEAD_API_KEY`·`GEMINI_API_KEY`·`CONTROL_SHEET_URL`·`GOOGLE_CREDENTIALS_JSON`. OAuth 불필요)와 **엔진 전용 DB 세션**(`/data/state.db`)을 둔다.
- 엔진은 멀티유저 진행작업(`app/config`·`app/db`)에 **의존하지 않는다** → Railway에서 OAuth env 없이 독립 부팅.

### Smartlead API (공식 문서 기준 확정)
- 리드 추가: `POST https://server.smartlead.ai/api/v1/campaigns/{campaign_id}/leads?api_key=…`
  ```json
  { "lead_list": [ { "email": "...", "first_name": "...", "company_name": "...",
                     "custom_fields": { "job_title": "...", "source": "..." } } ],
    "settings": { "ignore_global_block_list": true,
                  "ignore_unsubscribe_list": true,
                  "ignore_duplicate_leads_in_other_campaign": true } }
  ```
  요청당 최대 100건. 응답의 추가/중복/실패 카운트로 행별 `push_status` 판정.
- 통계(폴링): 캠페인 statistics/analytics 엔드포인트에서 `sent`/`bounce` 카운트 수집.
- 참고: api.smartlead.ai/api-reference/campaigns/add-leads , smartlead.readme.io/reference/add-leads-to-a-campaign-by-id

### 볼륨
Railway `/data` 볼륨 추가, `state.db` 보관.

### 의존성 추가 (`requirements.txt`)
```
apscheduler        # 시간 트리거
dnspython          # MX 조회
google-genai       # Gemini API (또는 google-generativeai)
# gspread, sqlalchemy, httpx 등 기존 보유
```

### 롤백 안전성
- 신규 기능은 엔진(HourlyTick)·신규 서비스 모듈로 격리. 기존 크롤/CSV/시트 export 라우트는 동작 변경 없음.
- 엔진 미등록 시 기존 앱과 동일 동작 → 문제 시 엔진만 끄면 됨.

### 기존 코드 정돈 (함께 처리, 최소 범위)
- `server.py` 중복 `/api/export/sheet` 라우트 정리, CORS 설정 정합 (선행 리뷰 발견 항목 중 충돌분만).
- `GoogleSheetExporter`를 다중 탭(설정/스케줄/내역/경고) 다룰 수 있게 확장.

---

## 10. 테스트 전략

### 단위 (pytest)
| 대상 | 포인트 |
|------|--------|
| CrawlerService | wanted 포함 3사 동일 인터페이스(crawl_with_emails) / 어댑터 |
| SchedulePlanner | N회분 top-up / 주기 간격 / 비어있지 않은 키워드·기존 예정 행 보존 / 회피목록 |
| KeywordResolver | 키워드 있으면 그대로 / 비면 Gemini / Gemini 실패 시 보류 |
| EmailValidator | 문법 / MX 모킹 / 시스템주소·일회용 제외 / 역할주소 포함 / 캐시·TTL |
| DedupStore | **accepted만** 제외 기준 / suspended·failed는 재시도 가능 / 정규화 / backfill(accepted만) |
| SmartleadClient | 배치 분할(100) / 공식 파라미터 / 401·429·4xx·5xx 분기 / 추가·중복·실패 → push_status |
| AlertMonitor | **delta·최소표본** 경계값 / 누적 오탐 안 남 / bounce_critical 시 suspend |
| SheetControl | ⚙️설정·📅스케줄 파싱·검증 / 예정일시 09:00 파싱 / 키워드 보호 규칙 / 상태 전이 |
| 트리거/락 | 예정일시 도래 판정 / **run_lock으로 같은 due 행 동시·중복 실행 차단** / Asia/Seoul |

### 통합 (TestClient + `:memory:` SQLite)
- HourlyTick 전체 1회 — 크롤/Gemini/Smartlead/Sheets 전부 mock, 예정표 top-up·도래행 실행·내역·경고 검증.
- 재실행 시 dedup으로 재푸시 0건, 완료행 재실행 안 됨.
- bounce_critical → 다음 tick 푸시 보류.

### 테스트 모드 분리
- `GEMINI_TEST_MODE=1`, `SMARTLEAD_TEST_MODE=1`(respx), `SHEETS_TEST_MODE=1`(in-memory), `MX` 모킹. 시간은 `freezegun`.

---

## 11. 구현 단계 개요 (writing-plans에서 상세화)

0. **선행: WantedCrawler 호환** — `WantedCrawler.crawl_with_emails()` 추가 또는 CrawlerService 공통 어댑터(search→detail→extract)로 시그니처 통일. (지금 wanted는 `/api/crawl`에서 크래시)
1. **EngineSettings 분리** + SQLite `state.db`(engine_state/pushed_emails/mx_cache/run_lock) + 엔진 전용 세션. `app/config`·`app/db`(OAuth) 비의존.
2. `services/` 모듈 골격 분리.
3. SheetControl — `⚙️설정`/`📅키워드스케줄` 읽기·검증(예정일시 09:00 파싱, 키워드 보호 규칙) + `발송내역`(push_status 컬럼)/`⚠️경고` append + 상태 전이.
4. EmailValidator — 문법 + MX(dnspython, 캐시) + 시스템주소/일회용 제외.
5. DedupStore — `accepted`만 기준 대조 + backfill.
6. GeminiClient + KeywordResolver(키워드 비면만 채움).
7. SchedulePlanner — 예정표 top-up(주기 간격, 회피목록, 비어있지 않은 키워드 보존).
8. SmartleadClient — 리드 배치 푸시(공식 파라미터) + 통계 조회 + push_status 매핑.
9. AlertMonitor — delta·최소표본 bounce 판정 + suspend + ⚠️경고.
10. HourlyTick + RunPipeline 조립 + run_lock/running 전이 + APScheduler(1h, `max_instances=1, coalesce=True`, Asia/Seoul) + 부팅 시 고아 락 정리 + `/healthz`.
11. 기존 코드 정돈(중복 라우트·CORS).
12. 단위/통합 테스트 + 테스트 모드.
13. Railway 배포(볼륨, 환경변수, 의존성) + 컨트롤 시트 템플릿 생성.

---

## 12. 열린 질문 / 향후
- **bounce_critical 재개 UX**: ⚙️설정 토글 vs 자동 쿨다운 — 구현 계획에서 확정.
- **Gemini 키워드 개수/프롬프트 튜닝**: 초기 키워드 수·예정표 N=5, 운영하며 조정.
- **웹 관리 대시보드 / 관리자 화면**: 1차는 시트가 대시보드. 이후 별도 작업으로 웹 UI·관리자 도입 예정.
- **이메일 알림**: 1차는 시트 경고. 필요 시 Gmail 발신 추가.
- **캐치올 정밀 검증/외부 검증 API**: 바운스가 여전히 높으면 2차에서 외부 검증(ZeroBounce 등) 도입 검토.
- **다중 캠페인/산업군 확장**: ⚙️설정 다행으로 이미 지원. 규모 커지면 실행 시간/쿼터 점검.
</content>
