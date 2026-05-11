# 멀티유저 크롤 · 검증 · Smartlead 푸시 · 스케줄링 디자인

**작성일**: 2026-05-11
**대상 코드베이스**: `/Users/uhuru/dev/emailmak-main` (Email Crawler)
**상태**: 초안 — 사용자 리뷰 대기

---

## 1. 배경과 목표

### 현재 상태

- FastAPI 단일 컨테이너로 운영 중인 채용 사이트(사람인/잡코리아/원티드) 이메일 크롤러.
- 누구나 접속 가능 (인증 없음). 결과는 CSV 다운로드 또는 단일 공용 Google Sheets로 내보내기.
- 사이트가 내부·주변 약 20명에게 공유된 상태로 운영 중.

### 해결하려는 문제

1. **이메일 품질이 낮아 Smartlead 캠페인에서 바운스가 많이 발생**.
2. **수집 → 검증 → Smartlead 캠페인 리드 업로드를 매번 수동으로** 하고 있어 손이 많이 감.
3. **사용자별로 Smartlead 계정/캠페인이 달라야** 하는데 현재는 단일 인스턴스 공용 사용.

### 목표

- 도메인 단위 중복 제거, 블랙리스트(개인+팀), 발송이력 자동 제외로 같은 회사에 중복/원치 않는 발송 방지.
- SMTP(MX + RCPT TO + 캐치올 감지) 기반 이메일 유효성 검증으로 바운스율을 구조적으로 낮춤.
- 사용자가 등록한 키워드/캠페인을 스케줄(cron)에 따라 자동 크롤·검증·푸시.
- 멀티유저 격리(Google OAuth) — 각자 자기 Smartlead 키·시트·블랙리스트·이력만 다룸.
- 익명 사용자는 기존의 크롤링·CSV·시트 내보내기 기능을 그대로 사용 가능 (회귀 없음).

### 비목표 (Out of Scope)

- 조직/관리자/일반 사용자 권한 구분.
- 캠페인 답장률·오픈율 대시보드, Prometheus/Grafana 메트릭.
- LLM 기반 이메일 분류·콜드메일 초안 생성.
- 사용자 시트 자동 생성 (사용자가 만든 시트 URL을 입력하는 방식만 지원).
- 캐치올 도메인 휴리스틱 우회.

---

## 2. 핵심 결정 요약

| 영역 | 결정 |
|------|------|
| 데이터 품질 항목 | ① SMTP 유효성 검증, ③ 회사 중복 통합, ④ 블랙리스트, ⑤ Smartlead 푸시 |
| 워크플로우 시점 | 하이브리드 — 중복/블랙리스트는 실시간, SMTP 검증은 푸시 직전 일괄 |
| Smartlead UX | 캠페인 드롭다운(API), 푸시 직전 1회 요약 다이얼로그, 캐치올/역할 이메일은 기본 OFF |
| SMTP 검증 깊이 | MX + SMTP RCPT TO + 캐치올 감지 (도메인당 1동시, 7일 캐시, 타임아웃 10초) |
| 블랙리스트 단위 | 도메인 단위 |
| 블랙리스트 구조 | 개인 + 팀 공통 두 층, 모두 편집 가능 |
| 인증 | Google OAuth, 화이트리스트(도메인 또는 이메일 명단) |
| 인증 적용 범위 | 익명: 크롤·CSV·시트 내보내기. 로그인 필요: 검증·푸시·스케줄·블랙리스트·이력 |
| 스케줄 아키텍처 | 결정론적 워커 파이프라인 (APScheduler 내장), LLM 미사용 |
| 무인 안전장치 | 드라이런 기본 / 회로차단기 / 일일 푸시 상한 / 캐치올·역할이메일 자동 제외 / 실패 알림 |
| 저장소 | SQLite (Railway 볼륨)가 source of truth, Google Sheets는 미러·백업 |
| 사용자 규모 | 최대 20명 / 내부 사용자 |

---

## 3. 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│                         Browser (Vanilla JS)                     │
│   익명: 크롤링 UI   |   로그인 후: 스케줄/푸시/이력/블랙리스트   │
└──────────────────────────────────────────────────────────────────┘
                                │  HTTP / SSE
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                       FastAPI App (server.py)                    │
│                                                                  │
│  ┌─ 인증 미들웨어 (Google OAuth, 세션 쿠키) ─────────────────┐   │
│  │   익명 허용: /, /api/crawl/*, /api/export/sheet            │   │
│  │   로그인 필수: /api/validate, /api/smartlead/*,            │   │
│  │                /api/schedule/*, /api/blacklist/*           │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Routers:                                                        │
│    • crawl_router      (기존 + 정제: 중복/블랙리스트 자동 적용)  │
│    • validate_router   (SMTP+캐치올 검증)                        │
│    • smartlead_router  (캠페인 목록/푸시, 푸시 직전 요약)        │
│    • schedule_router   (스케줄 작업 CRUD, dryrun→live 안내)      │
│    • blacklist_router  (개인+팀 CRUD)                            │
│    • auth_router       (OAuth start/callback/logout)             │
│                                                                  │
│  Services:                                                       │
│    • CrawlerService     (기존 saramin/jobkorea/wanted 통합)      │
│    • EmailValidator     (MX, SMTP RCPT, catch-all)               │
│    • SmartleadClient    (사용자 키별 분리)                       │
│    • BlacklistService   (개인+팀 머지)                           │
│    • DedupService       (회사 단위 통합)                         │
│    • HistoryService     (발송이력 적재, 자동 제외)               │
│                                                                  │
│  Workers (APScheduler 내장):                                     │
│    • ScheduleRunner — cron 트리거                                │
│    • CrawlerWorker → ValidatorWorker → PusherWorker (순차)       │
│    • CircuitBreaker — 임계치 미달 시 자동 중단                   │
│    • SheetSyncWorker — 사용자별 5분 주기                         │
└──────────────────────────────────────────────────────────────────┘
                  │                                  │
                  ▼                                  ▼
   ┌──────────────────────────┐      ┌──────────────────────────┐
   │  SQLite (Railway Volume) │      │  Google Sheets (사용자별) │
   │  source of truth         │      │  미러 / 백업              │
   └──────────────────────────┘      └──────────────────────────┘
                                                 │
                                                 ▼
                                    ┌────────────────────┐
                                    │   Smartlead API    │
                                    │   사용자별 키 분리 │
                                    └────────────────────┘
```

### 컴포넌트 책임 경계

- **Router**: HTTP 입출력 + 인증 가드. 비즈니스 로직 없음.
- **Service**: 도메인 규칙. DB · 외부 API를 다루지만 HTTP 모름.
- **Worker**: 시간/스케줄 트리거에 따라 Service들을 조립해서 실행.
- **Auth 미들웨어**: 라우트 단위 권한 데코레이터(`@require_login`). 비즈니스 코드는 인증 신경 안 씀.

각 컴포넌트는 인터페이스 명확, 독립 테스트 가능. 파일은 책임당 1개로 분리 (현재 단일 `server.py`에 모인 코드를 라우터·서비스로 쪼개는 작업이 포함됨 — "작업 중인 코드를 정돈"하는 차원).

---

## 4. 데이터 모델

### SQLite 스키마 (`data/app.db`, Railway 볼륨)

```sql
-- 1. 사용자
CREATE TABLE users (
  id              INTEGER PRIMARY KEY,
  google_sub      TEXT NOT NULL UNIQUE,
  email           TEXT NOT NULL UNIQUE,
  name            TEXT,
  sheet_url       TEXT,
  smartlead_key   TEXT,                        -- Fernet 암호화
  created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_login_at   TIMESTAMP
);

-- 2. 스케줄 작업
CREATE TABLE schedule_jobs (
  id                    INTEGER PRIMARY KEY,
  user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name                  TEXT NOT NULL,
  keyword               TEXT NOT NULL,
  source                TEXT NOT NULL,         -- saramin/jobkorea/wanted
  start_page            INTEGER DEFAULT 1,
  end_page              INTEGER DEFAULT 5,
  cron                  TEXT NOT NULL,
  smartlead_campaign_id TEXT NOT NULL,
  mode                  TEXT NOT NULL DEFAULT 'dryrun',
  enabled               BOOLEAN NOT NULL DEFAULT 1,
  dryrun_success_count  INTEGER DEFAULT 0,
  next_run_at           TIMESTAMP,
  last_run_at           TIMESTAMP,
  created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_jobs_runnable ON schedule_jobs(enabled, next_run_at);

-- 3. 개인 블랙리스트
CREATE TABLE personal_blacklist (
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  domain      TEXT NOT NULL,
  note        TEXT,
  source      TEXT,                            -- manual / bounce_webhook / sheet
  added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, domain)
);

-- 4. 팀 공통 블랙리스트
CREATE TABLE team_blacklist (
  id                INTEGER PRIMARY KEY,
  domain            TEXT NOT NULL UNIQUE,
  note              TEXT,
  added_by_user_id  INTEGER REFERENCES users(id),
  added_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. 발송이력
CREATE TABLE send_history (
  id              INTEGER PRIMARY KEY,
  user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  domain          TEXT NOT NULL,
  email           TEXT NOT NULL,
  company_name    TEXT,
  campaign_id     TEXT,
  keyword         TEXT,
  sent_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_history_lookup ON send_history(user_id, domain);

-- 6. 실행 로그
CREATE TABLE run_logs (
  id                INTEGER PRIMARY KEY,
  schedule_job_id   INTEGER REFERENCES schedule_jobs(id) ON DELETE SET NULL,
  user_id           INTEGER NOT NULL REFERENCES users(id),
  trigger           TEXT NOT NULL,             -- schedule / manual
  started_at        TIMESTAMP NOT NULL,
  finished_at       TIMESTAMP,
  status            TEXT NOT NULL,             -- running / success / failed / circuit_open
  crawled_count     INTEGER DEFAULT 0,
  validated_pass    INTEGER DEFAULT 0,
  validated_fail    INTEGER DEFAULT 0,
  catchall_count    INTEGER DEFAULT 0,
  role_email_count  INTEGER DEFAULT 0,
  pushed_count      INTEGER DEFAULT 0,
  error_message     TEXT
);

-- 7. 검증 캐시 (전역, 사용자 공유 — 도메인 단위라 안전)
CREATE TABLE validation_cache (
  domain        TEXT PRIMARY KEY,
  mx_valid      BOOLEAN,
  smtp_result   TEXT,                          -- ok / no_user / catchall / timeout / refused
  is_catchall   BOOLEAN,
  checked_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Google Sheets 미러 구조 (사용자 시트에 자동 생성/유지)

| 시트명 | 컬럼 | 역할 | 동기화 방향 |
|--------|------|------|------------|
| `결과_YYYYMMDD` (기존) | 회사명, 채용공고, 대표이메일, 추가이메일, 홈페이지, 채용링크, 기업링크, 출처, 수집날짜 | 한 회 크롤링 결과 | 즉시 기록 (기존 동작) |
| `발송명단` (기존) | (동일) | 누적, 필터링 | 즉시 기록 (기존 동작) |
| `발송이력` (신규) | 도메인, 이메일, 회사명, 캠페인, 키워드, 발송일 | 자동 제외 근거 | DB → 시트 |
| `블랙리스트` (신규) | 도메인, 메모, 추가일, 출처 | 사용자 편집 가능 | 양방향 (DB 우선) |
| `팀_블랙리스트` (신규, RO) | 도메인, 메모, 추가자, 추가일 | 읽기 전용 표시 | DB → 시트 |
| `스케줄작업` (신규, RO) | 이름, 키워드, 소스, 페이지, cron, 캠페인, 모드, 활성화 | 읽기 전용 백업 | DB → 시트 |
| `실행로그` (신규, RO) | 시작/끝, 작업명, 수집/검증/푸시 수, 상태, 에러 | 모니터링용 | DB → 시트 |

### 시트 ↔ DB 동기화 규칙

- DB가 source of truth. 충돌 시 DB 우선.
- 단방향(DB → 시트, 5분): `발송이력`, `실행로그`, `팀_블랙리스트`, `스케줄작업`. 변경된 행만 incremental update (`last_synced_at` 추적).
- 양방향(`블랙리스트`만, 5분): 시트에만 있는 도메인 → `source='sheet'`로 INSERT, DB에 `source='sheet'`인데 시트에 없는 도메인 → DELETE. `manual`/`bounce_webhook` source 행은 보존.
- 사용자별 큐로 직렬화: A의 sync 실패가 B에 영향 없음.

### 시크릿 보호

- Smartlead API 키는 `APP_SECRET_KEY` 환경변수에서 파생한 Fernet 키로 AES 암호화 후 저장.
- 평문은 메모리 내에서만 존재.
- 로깅 시 자동 마스킹(`sk-***...xyz`, `j***@example.com`).

---

## 5. 데이터 흐름

### Flow 1 — 익명 크롤링 (기존 그대로, 변경 없음)

```
User → Frontend → /api/crawl/stream (SSE) → CrawlerService → 결과 카드 + CSV/Sheets 내보내기
```

### Flow 2 — 로그인 사용자: 수동 크롤링 → Smartlead 푸시

1. 사용자가 "Smartlead 보내기" 클릭.
2. `GET /api/smartlead/campaigns` → 캠페인 드롭다운 로드.
3. 캠페인 선택 후 "푸시 시작" 클릭.
4. 백엔드: `DedupService` → `BlacklistService` → `HistoryService` 자동 제외 적용.
5. `EmailValidator`가 남은 도메인 SMTP 검증 (캐시 활용, SSE로 진행률).
6. 검증 결과 요약 다이얼로그 1회 표시:
   ```
   푸시 대상: 47개
   ├─ ✅ 검증 통과: 32개  → 푸시 예정
   ├─ ⚠️ 캐치올: 8개      → [ ] 포함 (기본 OFF)
   ├─ 🏢 역할 이메일: 5개  → [ ] 포함 (기본 OFF)
   ├─ ❌ 검증 실패: 2개    → 제외
   └─ 🚫 자동 제외: 12개
   ```
7. "푸시 확정" 누르면 `SmartleadClient`가 사용자 키로 배치 푸시.
8. 성공 응답 받은 리드만 `send_history` 적재 + `run_logs` 기록.

### Flow 3 — 스케줄 작업 자동 실행 (무인)

매 분 APScheduler tick에서 `enabled=1 AND next_run_at<=now` 작업을 찾아 실행.

```
ScheduleRunner.execute(job):
  1. run_logs(status=running) 행 생성
  2. CrawlerWorker: source/keyword/pages 크롤링 → crawled_count
  3. DedupService → BlacklistService → HistoryService 자동 제외
  4. EmailValidator (캐시 활용) → validated_pass/fail/catchall 기록
  5. CircuitBreaker:
       검증 통과율 < CIRCUIT_BREAKER_THRESHOLD (기본 0.30) →
         job.enabled=0, status=circuit_open, 사용자 알림, 종료
  6. Mode 분기:
       dryrun: 푸시 안 함, "푸시 예정"만 시뮬레이션
       live:   PusherWorker 호출
  7. PusherWorker (live):
       Smartlead API 호출, 일일 상한(SMARTLEAD_DAILY_LIMIT) 적용
       응답 200 → send_history 적재
       4xx/401 → 즉시 중단, 알림
       429 → 백오프 후 재시도 (최대 5회), 남은 건 다음 tick에 이어서
  8. Dryrun 졸업 안내 (mode=dryrun):
       검증 통과율 >= 0.60으로 DRYRUN_GRADUATION_RUNS(기본 3)회 연속 →
         사용자에게 "라이브 전환 OK" 배너 (자동 전환 X, 1클릭 전환)
  9. run_logs(status=success, finished_at) 업데이트
 10. next_run_at = cron 계산
```

### Flow 4 — Smartlead 바운스 → 자동 블랙리스트 적재

Smartlead → `POST /api/webhooks/smartlead/bounce`
- HMAC 검증 (Smartlead webhook secret).
- payload의 `campaign_id`로 owner user 매핑.
- `personal_blacklist`에 `(user_id, domain, source='bounce_webhook')` INSERT.
- 다음 sync 주기에 시트 미러링.

### Flow 5 — 시트 동기화 (사용자별 5분 주기)

```
SheetSyncWorker (APScheduler interval=5min, 앱 부팅 시 등록):
  for each user WHERE sheet_url IS NOT NULL:
    DB → 시트: 발송이력, 실행로그, 팀_블랙리스트, 스케줄작업 (incremental)
    시트 → DB: 개인 블랙리스트만 (시트 도메인 셋 vs DB source='sheet' 도메인 셋 diff)
```

새 사용자 온보딩 직후엔 즉시 1회 sync로 미러 시트들을 생성/초기화 → 그 다음부터 5분 주기.

---

## 6. 안전장치 (무인 자동화 가드레일)

| # | 안전장치 | 위치 | 효과 |
|---|---------|------|------|
| 1 | 드라이런 기본 | `schedule_jobs.mode` 기본값 'dryrun' | 새 작업은 자동으로 첫 N회 푸시 안 함, 결과만 기록 |
| 2 | 회로차단기 | `ScheduleRunner` 검증 후 | 통과율 미달 시 작업 자동 비활성화 + 알림 |
| 3 | 일일 푸시 상한 | `PusherWorker` 사용자·캠페인 조합 카운터 | 같은 (user_id, campaign_id) 조합에 24시간 내 최대 `SMARTLEAD_DAILY_LIMIT`개. 초과분은 다음 날 큐에서 이어 진행. |
| 4 | 캐치올/역할이메일 자동 제외 | `ValidatorWorker` 후 `ModeFilter` | 무인 모드에서 강제 ON (수동 모드만 토글 가능) |
| 5 | 실패 알림 | run_logs status=failed/circuit_open 시 | 사용자 본인 이메일로 통보 |
| (보조) | 파서 0건 감지 | `CrawlerWorker` | 사이트 구조 변경 의심 → 작업 자동 비활성화 |

---

## 7. 에러 처리

| 단계 | 에러 | 처리 |
|------|------|------|
| 크롤링 | 네트워크/5xx | 도메인당 최대 3회 재시도(지수 백오프). 전부 실패 시 해당 회사 skip. |
| 크롤링 | 파싱 0건 | run_logs status=failed, error_message=`parser_zero`, 작업 비활성화 + 알림. |
| 크롤링 | 403/429 봇 차단 | 30초 백오프 1회 재시도. 재실패 시 작업만 중단(enabled 유지). |
| SMTP | 타임아웃 (10초) | smtp_result=`timeout`. 무인 모드에서 제외. |
| SMTP | RCPT 거절 | smtp_result=`no_user`. 제외. |
| SMTP | 메일서버 IP 차단 | 도메인 검증 skip, "검증 불가"로 표시. 무인에서도 통과. |
| SMTP | DNS 실패(MX 없음) | 도메인 캐싱(TTL 7일). 같은 도메인 다른 이메일도 자동 제외. |
| Smartlead | 4xx | 즉시 중단, 응답 본문 기록, 사용자 알림. 다른 사용자 영향 없음. |
| Smartlead | 401 | 사용자 알림 + 앱 내 "키 재입력" 배너. 해당 사용자 푸시 일시 정지. |
| Smartlead | 429 | 60초 백오프, 최대 5회. 그래도 실패면 큐 보관, 다음 tick 이어서. |
| Smartlead | 5xx | 3회 지수 백오프. 큐 보관 후 다음 실행 재진행. |
| 시트 sync | 권한 만료/시트 삭제 | 사용자 알림 + 시트 URL 재입력 안내. DB 정상. |
| 시트 sync | API rate limit | 사용자 큐 직렬화, 주기 자동 10분으로 연장. |
| OAuth | callback 실패 | 로그인 페이지 + 에러 토스트. |
| OAuth | 세션 만료 | 로그인 필수 라우트만 401, 익명 라우트는 영향 없음. |
| DB | 락 충돌 | SQLite WAL + busy_timeout=5s. |
| DB | 디스크 풀/볼륨 장애 | `/healthz` 실패 → Railway 컨테이너 재시작. |

### 멱등성과 재실행 안전성

- **send_history는 푸시 응답 200 받은 다음 적재**. 실패한 도메인은 다음 실행에서 재시도.
- **PusherWorker는 리드 단위 트랜잭션**. N개 중 M개에서 멈춰도 M개는 history에 기록되어 다음 실행에서 자동 제외.
- **CrawlerWorker는 멱등 아님** (검색 결과는 시점마다 다름). 재실행 시 같은 회사가 다시 수집될 수 있으나 history/blacklist로 자동 제외 → 중복 푸시 없음.

---

## 8. 관측성

**3계층 로깅**:

1. **DB `run_logs`** — 한 번의 실행 = 1행. 앱 UI에서 조회 (`/runs?job=<id>`).
2. **구조화 stdout JSON 로그** — Railway 콘솔 검색용. 민감 정보 마스킹.
3. **Google Sheet `실행로그`** — 앱 미접속 상태에서도 시트로 확인.

**Health check**: `GET /healthz` — DB ping + 디스크 여유 체크.

**알림**: 사용자 본인 이메일 (Google OAuth 이메일)로 전송. SMTP는 `NOTIFY_FROM_EMAIL` + Gmail 앱비밀번호 환경변수 사용.

**알림 트리거**:
- 작업 자동 비활성화 (parser_zero, circuit_open)
- Smartlead 키 무효 (401)
- 시트 권한 만료

---

## 9. 인증 및 권한

### OAuth 흐름

1. 사용자가 "Google로 시작하기" 클릭 → `GET /api/auth/start` → Google 동의 화면.
2. Google이 `GET /api/auth/callback`로 리다이렉트 → 토큰 교환 → 이메일 추출.
3. 화이트리스트 검증 (둘 다 설정 시 OR 매칭 — 어느 한쪽이라도 통과하면 허용):
   - `ALLOWED_OAUTH_DOMAIN`(콤마구분 가능)이 설정되어 있으면 이메일 도메인 일치 여부 확인.
   - `ALLOWED_OAUTH_EMAILS`(콤마구분)이 설정되어 있으면 이메일 일치 여부 확인.
   - 둘 다 미설정 시 모든 Google 계정 허용 (개발/로컬용). 프로덕션에서는 최소 한쪽 필수.
   - 매칭 실패 → 403 + "권한 없음" 페이지.
4. `users` upsert (`google_sub` 기준), `last_login_at` 갱신.
5. 세션 쿠키 발급(`itsdangerous` 서명, HttpOnly, Secure, SameSite=Lax, 30일).
6. 처음 로그인이면 온보딩 페이지로 리다이렉트 — Smartlead API 키 + Google Sheet URL 입력.

### 라우트 권한

- **익명 허용**: `/`, `/static/*`, `/api/crawl`, `/api/crawl/stream`, `/api/export/sheet`, `/api/config/google-sheet`, `/api/auth/*`, `/api/webhooks/smartlead/*`, `/healthz`.
- **로그인 필수** (`@require_login`): 그 외 모든 `/api/*`.

### 데이터 격리

- 로그인 필수 라우트는 모두 `request.state.user.id`를 받아 `WHERE user_id = ?` 자동 적용.
- 검증 캐시(`validation_cache`)는 도메인 단위라 사용자 간 공유 (PII 없음).
- 팀 블랙리스트는 모든 로그인 사용자가 읽기/추가 가능.

---

## 10. 테스트 전략

### 단위 테스트 (pytest)

| 대상 | 포인트 |
|------|--------|
| `EmailValidator` | MX 모킹 / SMTP 응답 모킹 / 캐치올 감지(랜덤 주소 250 OK) / 캐시 / 타임아웃 |
| `BlacklistService` | 개인+팀 머지 / 대소문자·www. 정규화 / 시트 sync 양방향 |
| `DedupService` | 같은 회사 다중 소스 통합 / 회사명 표기 차이 |
| `HistoryService` | 동일 도메인 자동 제외 / 사용자 간 격리 |
| `CircuitBreaker` | 임계치 미달 → enabled=0 / 정상 통과 |
| `SmartleadClient` | 401/429/4xx/5xx 분기 / 응답 파싱 |
| cron 계산 | next_run_at 정확성 / Asia/Seoul 타임존 |

### 통합 테스트 (FastAPI TestClient + `:memory:` SQLite)

| 시나리오 |
|---------|
| 익명 크롤링 SSE (외부 사이트 mock) |
| 익명 시트 export (gspread mock) |
| 로그인 필수 라우트 익명 호출 → 401 |
| OAuth callback → 세션 쿠키 → 사용자 라우트 접근 |
| A 사용자 블랙리스트가 B에 안 보임 |
| 스케줄 작업 CRUD + cron 검증 |
| 시트 sync 후 DB ↔ 시트 일치 |

### 테스트 환경 분리

- `SMTP_TEST_MODE=1`: SMTP 호출 → 픽스처 응답.
- `SMARTLEAD_TEST_MODE=1`: API → mock (respx).
- `SHEETS_TEST_MODE=1`: gspread → in-memory.
- 스케줄러는 `ScheduleRunner.execute(job)` 직접 호출, 시간은 `freezegun`.

### E2E (Playwright, 1~2개)

- 로그인 → 스케줄 작업 생성 → 수동 트리거 → 발송이력 행 추가 확인.
- 익명 크롤링 → CSV 다운로드 (회귀 방지).

---

## 11. 배포

### Railway 환경변수 (신규 추가)

```
APP_SECRET_KEY              (Fernet 키 시드, 세션 서명)
GOOGLE_OAUTH_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET
ALLOWED_OAUTH_DOMAIN        (예: "yourcompany.com")
# 또는
ALLOWED_OAUTH_EMAILS        (콤마구분 화이트리스트)

NOTIFY_FROM_EMAIL           (Gmail 발신 주소)
NOTIFY_SMTP_PASSWORD        (Gmail 앱비밀번호)

SMARTLEAD_DAILY_LIMIT       (기본 200)
CIRCUIT_BREAKER_THRESHOLD   (기본 0.30)
DRYRUN_GRADUATION_RUNS      (기본 3)
```

기존 `GOOGLE_CREDENTIALS_JSON`은 그대로 사용 (서비스 계정 = 봇 계정).

### 볼륨

Railway `/data` 볼륨 추가, SQLite 파일은 `/data/app.db`.

### 의존성 추가 (`requirements.txt`)

```
authlib
itsdangerous
cryptography
apscheduler
dnspython
aiosmtplib
alembic
sqlalchemy
croniter
respx          # 테스트
freezegun      # 테스트
pytest         # 테스트
pytest-asyncio # 테스트
```

### 마이그레이션 순서

1. SQLite 스키마 적용 (alembic). 빈 DB로 시작.
2. 기존 라우트는 시그니처 변경 없이 그대로 동작.
3. 첫 사용자(본인) 로그인 → 온보딩 (시트 URL + Smartlead 키 입력).
4. 다른 내부 사용자들 차례로 OAuth 로그인 → 각자 온보딩.
5. 익명 크롤링/CSV/시트 export는 회귀 없음.

### 롤백 안전성

- 신규 라우트는 모두 별도 prefix (`/api/auth/*`, `/api/schedule/*`, `/api/blacklist/*`, `/api/smartlead/*`, `/api/validate`, `/api/webhooks/*`).
- 기존 라우트는 동작 변경 없음.
- 문제 발생 시 신규 기능만 비활성화 가능 (feature flag 없이 라우터 등록만 제거).

### 기존 코드 정돈 (이 작업 중에 함께 정리)

리뷰에서 발견된 항목 중 이 디자인과 직접 충돌하는 것을 함께 수정:
- `server.py`에 중복된 `/api/export/sheet` 라우트 1개 제거.
- CORS `allow_origins=["*"] + allow_credentials=True` 모순 해결 (OAuth가 들어오면서 어차피 명시적 origin 필요).
- `BaseCrawler.search` 추상 시그니처와 구현 시그니처 정합.
- `/api/debug/jobkorea` 라우트는 환경변수(`ENABLE_DEBUG_ROUTES=1`)로 가드.
- 포트 일관화 (`server.py:__main__`의 8001 → 8000으로 정정).

위 항목들은 본 디자인 작업의 부수 효과로 정리하되, 별도 본질적 리팩토링은 하지 않음.

---

## 12. 구현 단계 개요 (writing-plans에서 상세화 예정)

대략적인 단계 — 자세한 작업 분할은 다음 writing-plans 단계에서 진행.

1. SQLite 스키마 + alembic 마이그레이션, 라우터/서비스 폴더 구조 분리.
2. Google OAuth + 세션 쿠키 + 라우트 가드 미들웨어.
3. 온보딩 화면 (시트 URL + Smartlead 키 입력) + 시크릿 암호화.
4. EmailValidator(MX + SMTP + 캐치올) + validation_cache.
5. BlacklistService (개인+팀 머지, 도메인 정규화).
6. DedupService + HistoryService.
7. SmartleadClient + 캠페인 드롭다운 + 수동 푸시 요약 다이얼로그.
8. 스케줄 작업 CRUD UI + APScheduler 등록/해제.
9. ScheduleRunner 파이프라인 + 안전장치(회로차단기, 일일 상한, 알림).
10. SheetSyncWorker (DB↔시트, 사용자별 5분).
11. Smartlead 바운스 webhook → 개인 블랙리스트 자동 적재.
12. 알림 이메일 모듈.
13. 통합/단위 테스트, E2E 1~2개.
14. 기존 코드 정돈 (위 11절 마지막 항목).
15. Railway 배포 (볼륨, 환경변수, alembic 마이그레이션 실행).

---

## 13. 열린 질문 / 향후 작업

- **사용자별 시트 자동 생성**: 1차에서는 사용자가 만든 시트 URL을 받음. 2차에서 봇 계정이 Drive에 자동 생성 → 사용자에게 공유 옵션 추가 고려.
- **AI 활용**: 캐치올 도메인의 담당자 추정, 콜드메일 초안 자동 생성, 회사 설명 요약 등 — 2차 이후 검토.
- **메트릭 대시보드**: Smartlead 캠페인 성과(오픈/클릭/답장률)를 가져와 검증 임계치 자동 튜닝 — 운영 데이터 쌓인 뒤 검토.
- **다중 조직(테넌트) 지원**: 현재 평등한 팀원 모델. 조직 분리가 필요해지면 `organizations` 테이블 추가.
- **관리자 권한**: 1차에서는 전원 동등. 팀 블랙리스트 편집 권한 제한이 필요해지면 추가.
