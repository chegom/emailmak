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
4. 관리 UI를 따로 만들고 쓰는 건 번거롭다 → **구글 시트 한 장에서 다 관리**하고 싶다.

### 목표
- **3일 주기**로 자동: 산업군 → 키워드 → 크롤 → 검증 → Smartlead 캠페인 리드 투입 → 시트에 내역 누적.
- **키워드 하이브리드**: 사용자가 시트에 직접 적으면 그걸 사용, 비우면 **Gemini가 산업군 기반으로 추천** (최근 사용 키워드 회피 → 중복↓).
- **사전 검증**으로 바운스 줄이기: MX + 문법 + 시스템주소/일회용 도메인 제외 (Railway 포트25 차단 환경에서 동작 가능한 범위).
- **사후 경고**: Smartlead 통계를 폴링해 bounce율/이슈가 임계치를 넘으면 시트 `⚠️경고` 탭에 기록.
- **시트 = 컨트롤 패널 겸 DB**: 사람이 만지는 노브(산업군·사이트·캠페인·키워드·on/off)와 출력(내역·경고·사용키워드)을 전부 한 시트에서.

### 비목표 (Out of Scope)
- 멀티유저 / Google OAuth / 사용자별 격리.
- SMTP `RCPT TO` 실사서함 검증 (Railway 아웃바운드 25번 포트 차단으로 불가).
- 캐치올(catch-all) 도메인 정밀 감지.
- 블랙리스트(개인/팀), 바운스 웹훅 수신.
- 콜드메일 본문 AI 생성, 캠페인 성과(오픈/클릭/답장) 대시보드.

---

## 2. 핵심 결정 요약

| 영역 | 결정 |
|------|------|
| 범위 | 단일 사용자 · 시트 주도 · 무화면 엔진 |
| 트리거 | 스케줄 자동, **3일 주기**, Asia/Seoul |
| 키워드 | 하이브리드 — 시트 수동 입력 우선, 비면 **Gemini 2.5 Flash** 자동 생성(최근 사용 회피) |
| 검증 | **MX + 문법 + 시스템주소/일회용 제외** (역할주소는 포함) |
| 역할주소 정책 | `recruit@ hr@ info@ sales@ contact@` 등 업무용 역할주소 **포함**(주 타깃), `no-reply@ postmaster@ mailer-daemon@ noreply@ donotreply@` 등 시스템주소만 제외. 시트에 역할주소 여부 표시 |
| 중복 제거 | `발송내역` 시트의 이메일 대조 + Smartlead `ignore_duplicate` 옵션 ON |
| Smartlead 푸시 | 캠페인에 리드 배치 투입(요청당 최대 100) |
| 경고 방식 | **폴링** — 매 실행 시 Smartlead 캠페인 통계 조회 (공개 웹훅 불필요) |
| 임계치 | bounce율 ≥5% ⚠️경고 / ≥8% 🚨심각(다음 자동 푸시 일시중단). 검증 통과율 <40% ⚠️. 크롤 0건 ⚠️ |
| 컨트롤 패널 | Google Sheets 1장 (`⚙️설정` / `사용키워드` / `발송내역` / `⚠️경고` 탭) |
| 상태 저장 | 경량 SQLite(Railway 볼륨) — 스케줄 마지막 실행 시각 + dedup 캐시. 시트가 사람용 source, DB는 엔진 내부용 |
| 시크릿 | `SMARTLEAD_API_KEY`, `GEMINI_API_KEY` 환경변수. `GOOGLE_CREDENTIALS_JSON` 재사용 |

---

## 3. 아키텍처

```
┌───────────────────────── Google Sheet (컨트롤 패널 = DB) ─────────────────────────┐
│  ⚙️설정   (사람 입력)  : 산업군, 사이트, 캠페인ID, 수동키워드(선택), 활성화        │
│  사용키워드 (엔진 기록): 산업군, 키워드, 출처(manual/ai), 생성일, 실행ID          │
│  발송내역  (엔진 기록) : 회사, 이메일, 산업군, 키워드, 사이트, 캠페인, 검증결과,    │
│                          역할주소여부, 푸시일시   ← 중복제거 기준                  │
│  ⚠️경고    (엔진 기록) : 일시, 종류(bounce/crawl0/lowpass/api_error), 상세, 수치   │
└───────────────────────────────────────────────────────────────────────────────────┘
        ▲ 읽기 (⚙️설정, 사용키워드, 발송내역)        │ 쓰기 (사용키워드, 발송내역, ⚠️경고)
        │                                            ▼
┌──────────────────────── FastAPI App (Railway, 무화면 엔진) ────────────────────────┐
│  Scheduler (APScheduler, 3일 주기, Asia/Seoul)                                      │
│    └─ RunPipeline.execute():                                                        │
│         1) SheetControl.read_settings()        ⚙️설정 파싱·검증                      │
│         2) KeywordResolver.resolve()           수동 우선 / 없으면 GeminiClient      │
│         3) CrawlerService.crawl()              기존 saramin/jobkorea/wanted 재사용  │
│         4) EmailValidator.validate()           MX + 문법 + 시스템/일회용 제외        │
│         5) DedupStore.filter_new()             발송내역 + 로컬 캐시 대조            │
│         6) SmartleadClient.push_leads()        배치 100, ignore_duplicate ON        │
│         7) SheetRecorder.append()              사용키워드/발송내역 기록             │
│         8) AlertMonitor.check()                Smartlead 통계 폴링 → ⚠️경고 판정    │
│                                                                                    │
│  외부:  Gemini API (키워드)   |   Smartlead API (리드/통계)   |   기존 봇 시트계정  │
│  상태:  SQLite(/data/state.db) — last_run_at, pushed_email 캐시                     │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### 컴포넌트 책임 경계
- **SheetControl**: 시트 ↔ 파이썬 구조체 변환. `⚙️설정` 읽기/검증, 각 탭 append. gspread 래퍼. (`utils/google_sheets.py`의 `GoogleSheetExporter` 확장/재사용)
- **KeywordResolver**: "수동키워드 있으면 그대로, 없으면 GeminiClient 호출". 최근 사용 키워드(=`사용키워드` 탭)를 프롬프트에 전달해 회피.
- **GeminiClient**: 산업군 + 회피 목록 → 키워드 N개. 모델 `gemini-2.5-flash`. 실패 시 빈 결과 → 파이프라인은 ⚠️경고 남기고 해당 작업 skip.
- **CrawlerService**: 기존 크롤러 통합. 시그니처 변경 없음.
- **EmailValidator**: 도메인 MX 조회(dnspython, 7일 캐시) + 문법 + 시스템주소/일회용 도메인 제외. **SMTP 핸드셰이크 안 함.**
- **DedupStore**: `발송내역`의 이메일 집합 + 로컬 SQLite 캐시로 이미 푸시된 주소 제외.
- **SmartleadClient**: `POST /api/v1/campaigns/{id}/leads`(배치) + 통계 조회. 4xx/401/429/5xx 분기.
- **SheetRecorder**: 결과를 `사용키워드`/`발송내역`에 append, 경고를 `⚠️경고`에 append.
- **AlertMonitor**: 사전 지표(크롤0/통과율) + 폴링 지표(bounce율)로 임계치 판정 → 경고 + 필요 시 자동 푸시 중단 플래그.
- **Scheduler/RunPipeline**: 위 서비스를 순서대로 조립. 시간 트리거.

각 컴포넌트는 인터페이스가 명확하고 독립 테스트 가능. 현재 단일 `server.py`에 모인 로직을 `services/` 모듈로 분리하는 작업이 포함된다(작업 중 코드 정돈 차원).

---

## 4. 데이터 모델

### 4.1 Google Sheet 탭 스키마 (컨트롤 시트, `CONTROL_SHEET_URL`)

**`⚙️설정`** — 사람이 입력. 한 행 = 한 작업(job).

| 열 | 예시 | 설명 |
|----|------|------|
| 산업군 | `물류` | Gemini 키워드 생성 입력 |
| 사이트 | `saramin` | saramin / jobkorea / wanted (콤마로 복수 가능) |
| 캠페인ID | `123456` | Smartlead 캠페인. 거의 고정 |
| 수동키워드 | `3PL, 풀필먼트` | (선택) 비우면 AI 자동 생성 |
| 페이지 | `1-5` | (선택) 크롤 페이지 범위, 기본 1-5 |
| 활성화 | `Y` | Y/N. N이면 skip |

**`사용키워드`** — 엔진 기록(append). 열: `실행일시, 실행ID, 산업군, 키워드, 출처(manual/ai)`.

**`발송내역`** — 엔진 기록(append). **중복제거 기준.** 열: `푸시일시, 실행ID, 회사명, 이메일, 산업군, 키워드, 사이트, 캠페인ID, 검증결과(pass/role), 역할주소여부`.

**`⚠️경고`** — 엔진 기록(append). 열: `일시, 실행ID, 종류, 상세, 수치`.
- 종류: `crawl_zero` / `low_pass_rate` / `bounce_warn` / `bounce_critical` / `api_error` / `settings_invalid`.

### 4.2 로컬 상태 (SQLite, `/data/state.db`, Railway 볼륨)
엔진 내부용. 시트가 사람용 source of truth지만, 매 실행마다 시트를 풀스캔하면 느리고 API 쿼터를 먹으므로 캐시·스케줄 상태만 로컬 보관.

```sql
CREATE TABLE engine_state (
  key        TEXT PRIMARY KEY,        -- 'last_run_at' 등
  value      TEXT
);

CREATE TABLE pushed_emails (
  email        TEXT PRIMARY KEY,      -- 정규화(소문자) 이메일
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
```

부팅 시 `pushed_emails`가 비어 있으면(볼륨 초기화 등) `발송내역` 시트에서 1회 backfill.

### 4.3 시크릿 보호
- `SMARTLEAD_API_KEY`, `GEMINI_API_KEY`는 환경변수에서만 읽고 로그에 마스킹(`sk-***...xyz`).
- 시트에는 API 키를 저장하지 않는다 (시트는 공유 위험).

---

## 5. 데이터 흐름 — 3일 주기 실행

```
RunPipeline.execute(run_id):                # APScheduler tick (3일 주기, Asia/Seoul)
  1. settings = SheetControl.read_settings()       # ⚙️설정 활성(Y) 행들
     - 행 검증 실패 → ⚠️경고(settings_invalid), 해당 행 skip
  2. for each job in settings:
     a. keywords = KeywordResolver.resolve(job)
          - job.수동키워드 있으면 그대로
          - 없으면 GeminiClient(산업군, 최근 사용키워드 목록) → N개
          - 실패 → ⚠️경고(api_error), job skip
        SheetRecorder.append_keywords(run_id, job, keywords, 출처)
     b. companies = CrawlerService.crawl(job.사이트, keywords, job.페이지)
          - 0건 → ⚠️경고(crawl_zero)
     c. (valid, dropped) = EmailValidator.validate(companies)
          - 통과율 < 0.40 → ⚠️경고(low_pass_rate)
     d. fresh = DedupStore.filter_new(valid)        # 발송내역/캐시 대조
     e. if AlertMonitor.push_suspended(job.캠페인ID): # 직전 bounce_critical 이면
          ⚠️경고에 "푸시 보류" 기록, 푸시 skip (검증·기록만)
        else:
          result = SmartleadClient.push_leads(job.캠페인ID, fresh)  # 배치 100
          DedupStore.mark_pushed(result.accepted)
        SheetRecorder.append_history(run_id, job, valid, result)
  3. AlertMonitor.poll_bounce():                     # 캠페인별 통계 조회
       rate = bounced / max(sent, 1)
       rate ≥ 0.08 → ⚠️경고(bounce_critical) + push_suspend(campaign)
       rate ≥ 0.05 → ⚠️경고(bounce_warn)
  4. engine_state['last_run_at'] = now
```

### 멱등성·재실행 안전성
- **푸시 성공분만 `pushed_emails`/`발송내역`에 적재** → 중간 실패 시 다음 실행에서 미푸시분만 재시도.
- 크롤은 멱등 아님(시점마다 결과 다름)이나, dedup으로 같은 이메일 재푸시 없음.
- Smartlead `ignore_duplicate_leads_in_other_campaign` 등 옵션을 켜서 서버측에서도 2중 방어.
- 컨테이너 재시작 시: `last_run_at` 기준으로 다음 3일 시점 재계산. 실행 도중 죽으면 다음 tick에서 미완 job 재수행(중복은 dedup이 흡수).

---

## 6. 안전장치 (무인 자동화 가드레일)

| # | 안전장치 | 위치 | 효과 |
|---|---------|------|------|
| 1 | bounce 회로차단 | AlertMonitor.poll_bounce | bounce율 ≥8%면 해당 캠페인 자동 푸시 중단 + 🚨경고 |
| 2 | 검증 통과율 가드 | EmailValidator 후 | <40%면 ⚠️경고 (키워드/사이트 품질 의심) |
| 3 | 크롤 0건 감지 | CrawlerService 후 | 사이트 구조 변경/키워드 부적합 의심 → ⚠️경고 |
| 4 | 시스템주소·일회용 제외 | EmailValidator | 무인 모드 강제 ON |
| 5 | dedup 2중화 | DedupStore + Smartlead 옵션 | 동일 이메일 재발송 방지 |
| 6 | 설정 검증 | SheetControl | 잘못된 사이트/캠페인/페이지 → 행 skip + ⚠️경고 |
| 7 | 일일 푸시 상한(선택) | SmartleadClient | `SMARTLEAD_DAILY_LIMIT` 초과분 다음 실행으로 이월 |

> bounce_critical로 자동 중단된 캠페인은 사람이 `⚠️경고`를 보고 원인 처리 후, 재개 방법(예: ⚙️설정에 재개 표시 또는 상태 리셋)을 둔다 — 세부는 구현 계획에서 확정.

---

## 7. 에러 처리

| 단계 | 에러 | 처리 |
|------|------|------|
| 시트 읽기 | 권한/시트 없음 | 부팅·실행 실패 로그, 재시도. (사람 개입 필요) |
| 설정 파싱 | 잘못된 값 | 해당 행 skip + ⚠️경고(settings_invalid) |
| Gemini | 타임아웃/4xx/쿼터 | job skip + ⚠️경고(api_error). 수동키워드 있으면 영향 없음 |
| 크롤 | 네트워크/5xx | 회사당 최대 3회 지수 백오프, 실패분 skip |
| 크롤 | 403/429 봇차단 | 30초 백오프 1회 재시도, 재실패 시 해당 사이트 skip |
| MX 조회 | DNS 실패 | mx_valid=false 캐싱(7일), 해당 도메인 제외 |
| Smartlead | 4xx | 즉시 중단, 응답 본문 ⚠️경고 기록 |
| Smartlead | 401 | 푸시 중단 + ⚠️경고("키 확인") |
| Smartlead | 429 | 60초 백오프 최대 5회, 남은 건 다음 실행 이월 |
| Smartlead | 5xx | 3회 지수 백오프 후 이월 |
| 시트 쓰기 | rate limit | 백오프 후 재시도, 사용자별 큐 불필요(단일 사용자) |
| DB | 락 | SQLite WAL + busy_timeout=5s |
| DB | 볼륨 장애 | `/healthz` 실패 → Railway 재시작, pushed_emails는 시트에서 backfill |

---

## 8. 관측성
- **시트 `⚠️경고` 탭** — 사람이 보는 1차 알림.
- **시트 `발송내역`/`사용키워드`** — 매 실행의 처리 결과.
- **구조화 stdout 로그(JSON)** — Railway 콘솔 검색용, 시크릿 마스킹.
- **`GET /healthz`** — DB ping + 시트 접근 가능 여부 + 마지막 실행 시각 노출.
- (선택) 다음 단계에서 이메일 알림 추가 가능 — 1차는 시트 경고로 충분.

---

## 9. 배포

### 환경변수 (신규)
```
SMARTLEAD_API_KEY            # Smartlead 리드/통계 API
GEMINI_API_KEY              # 키워드 생성 (Gemini 2.5 Flash)
CONTROL_SHEET_URL          # 컨트롤 패널 시트 URL
# 임계치/주기 (기본값 있음, 선택)
RUN_INTERVAL_DAYS=3
BOUNCE_WARN=0.05
BOUNCE_CRITICAL=0.08
MIN_PASS_RATE=0.40
SMARTLEAD_DAILY_LIMIT=200
# 기존 재사용
GOOGLE_CREDENTIALS_JSON     # 시트 읽기/쓰기 (봇 서비스계정)
```
> 보안: 기존에 노출됐던 서비스계정 키(`crawler-bot@emailmarketing-485502`)는 폐기·재발급 권장(이전 작업의 후속).

### 볼륨
Railway `/data` 볼륨 추가, `state.db` 보관.

### 의존성 추가 (`requirements.txt`)
```
apscheduler        # 스케줄러
dnspython          # MX 조회
google-genai       # Gemini API (또는 google-generativeai)
# gspread, sqlalchemy, httpx 등 기존 보유
```

### 롤백 안전성
- 신규 기능은 엔진(스케줄러)·신규 서비스 모듈로 격리. 기존 크롤/CSV/시트 export 라우트는 동작 변경 없음.
- 스케줄러 미등록 시 기존 앱과 동일하게 동작 → 문제 시 엔진만 끄면 됨.

### 기존 코드 정돈 (함께 처리, 최소 범위)
- `server.py` 중복 `/api/export/sheet` 라우트 정리, CORS 설정 정합 (선행 리뷰 발견 항목 중 충돌분만).
- `GoogleSheetExporter`를 다중 탭(설정/내역/경고) 다룰 수 있게 확장.

---

## 10. 테스트 전략

### 단위 (pytest)
| 대상 | 포인트 |
|------|--------|
| KeywordResolver | 수동 우선 / 비면 Gemini 호출 / 회피목록 전달 / Gemini 실패 시 skip |
| EmailValidator | 문법 / MX 모킹 / 시스템주소·일회용 제외 / 역할주소 포함 / 캐시·TTL |
| DedupStore | 발송내역 대조 / 정규화(소문자) / backfill |
| SmartleadClient | 배치 분할(100) / 401·429·4xx·5xx 분기 / 통계 파싱 |
| AlertMonitor | 임계치 경계값 / bounce_critical 시 push_suspend |
| SheetControl | ⚙️설정 파싱·검증(잘못된 행 skip) |
| 스케줄 | 3일 주기 next_run 계산 / Asia/Seoul |

### 통합 (TestClient + `:memory:` SQLite)
- RunPipeline 전체 1회 — 크롤/Gemini/Smartlead/Sheets 전부 mock, 발송내역·경고 기록 검증.
- 재실행 시 dedup으로 재푸시 0건.
- bounce_critical → 다음 실행 푸시 보류.

### 테스트 모드 분리
- `GEMINI_TEST_MODE=1`, `SMARTLEAD_TEST_MODE=1`(respx), `SHEETS_TEST_MODE=1`(in-memory), `SMTP`/`MX` 모킹. 시간은 `freezegun`.

---

## 11. 구현 단계 개요 (writing-plans에서 상세화)

1. `services/` 모듈 분리 + SQLite `state.db`(engine_state/pushed_emails/mx_cache) + alembic.
2. SheetControl — `⚙️설정` 읽기/검증 + 4개 탭 append (GoogleSheetExporter 확장).
3. EmailValidator — 문법 + MX(dnspython, 캐시) + 시스템주소/일회용 제외.
4. DedupStore — 발송내역/캐시 대조 + backfill.
5. GeminiClient + KeywordResolver(하이브리드).
6. SmartleadClient — 리드 배치 푸시 + 통계 조회.
7. AlertMonitor — 임계치 판정 + push_suspend + ⚠️경고 기록.
8. RunPipeline 조립 + APScheduler(3일, Asia/Seoul) 등록 + `/healthz`.
9. 기존 코드 정돈(중복 라우트·CORS).
10. 단위/통합 테스트 + 테스트 모드.
11. Railway 배포(볼륨, 환경변수, 의존성). 컨트롤 시트 템플릿 생성.

---

## 12. 열린 질문 / 향후
- **bounce_critical 재개 UX**: ⚙️설정 토글 vs 자동 쿨다운 — 구현 계획에서 확정.
- **Gemini 키워드 개수/프롬프트 튜닝**: 초기 N=5~10, 운영하며 조정.
- **이메일 알림**: 1차는 시트 경고. 필요 시 Gmail 발신 추가.
- **캐치올 정밀 검증/외부 검증 API**: 바운스가 여전히 높으면 2차에서 외부 검증(ZeroBounce 등) 도입 검토.
- **다중 캠페인/산업군 확장**: ⚙️설정 다행으로 이미 지원. 규모 커지면 실행 시간/쿼터 점검.
</content>
</invoke>
