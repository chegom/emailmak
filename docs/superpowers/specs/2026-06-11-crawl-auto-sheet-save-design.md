# 크롤링 결과 자동 시트 저장 + 접근 보호 설계

- 작성일: 2026-06-11
- 브랜치: feat/sheet-smartlead-automation
- 범위: 수동 크롤링 UI(`static/` + `server.py`)의 시트 저장 UX 개선. 자동화 엔진(`engine/` 스케줄러)과는 별개.

## 1. 배경 / 문제

현재 수동 크롤링 흐름은 다음과 같다.

- 크롤링은 "크롤링 시작" 버튼으로 수동 실행 → 결과를 화면 카드로만 표시.
- 시트 저장은 별도 "구글 시트" 버튼 → 모달에서 **매번 시트 URL을 직접 입력** → 내보내기.
- 시트 URL은 저장되지 않음(성공 시 입력칸 초기화, `localStorage` 미사용) → **매번 붙여넣어야 함**.
- 앱에 접근 보호가 전혀 없음(정적 서빙, URL 아는 누구나 접속·크롤·시트 저장 가능).

사용자 결정:

- 크롤링 결과를 거의 거르지 않고 다 저장한다 → **자동 적재**가 유리.
- 여러 기기/장소에서 사용한다 → 시트 URL을 **서버에 고정**(브라우저 localStorage 아님).
- 시트 URL이 서버에 저장되므로 **접근 보호 필요** → 단일 사용자용 **공유 비밀번호 하나**.

## 2. 핵심 결정

| # | 결정 | 선택 | 비고 |
|---|------|------|------|
| 1 | 적재 방식 | 자동 적재 | 크롤 완료 시 자동 저장. 결과는 화면에도 유지 |
| 2 | 시트 URL 저장 위치 | 서버 `state.db`의 `EngineState`(key/value) 재사용 | 키: `crawl_sheet_url`. 추가 인프라 0, 재배포 불필요 |
| 3 | 접근 보호 | 공유 비밀번호 1개(`APP_PASSWORD` env) | 토큰 발급 후 모든 API 보호 |
| 4 | 멀티유저/OAuth | 도입 안 함 | 단일 사용자. untracked `app/` User 계층은 그대로 둠 |
| 5 | 자동 저장 토글 | 없음(YAGNI) | 항상 자동. 필요해지면 추가 |

## 3. 아키텍처 개요

```
[브라우저]                         [FastAPI 서버]            [저장]
 ┌──────────────┐  password       ┌──────────────┐
 │ 비밀번호 게이트 │ ───────────────▶│ POST /api/login│
 │ (첫 접속 1회)  │ ◀────token───── │  토큰 검증     │
 └──────────────┘                  └──────────────┘
 ┌──────────────┐  Authorization   ┌──────────────┐  EngineState
 │ 설정: 시트 지정 │ ◀──────────────▶│ /api/settings  │◀────────────▶ state.db
 └──────────────┘                  └──────────────┘  (key/value)
 ┌──────────────┐  crawl           ┌──────────────┐
 │ 크롤링 → 완료  │ ───────────────▶│ /api/crawl/... │
 │   ↓ 자동       │  export(토큰)    │ /api/export/   │──▶ Google Sheet
 │ 자동 저장 호출  │ ───────────────▶│   sheet        │   (서버가 저장된
 └──────────────┘                  └──────────────┘    URL 사용)
```

핵심 불변식: **시트 URL은 더 이상 프론트가 매번 보내지 않는다.** 서버가 `state.db`에서 읽어서 사용한다. (보안 + 자동화 동시 충족)

## 4. 컴포넌트별 상세

### 4.1 접근 보호 (공유 비밀번호)

- 서버 env: `APP_PASSWORD`(필수). 미설정 시 동작 정책: 미설정이면 보호 비활성(로컬 개발 편의) — 단, 배포 시 반드시 설정하도록 README/주석에 명시.
- `POST /api/login {password}` → 일치 시 토큰 반환, 불일치 시 401.
  - 토큰 = `sha256(APP_PASSWORD + 서버 고정 솔트)`의 hex. 만료 없음(단일 사용자, 단순화). 비밀번호 바뀌면 토큰 무효화됨.
- 프론트: 토큰을 `localStorage`에 저장. 모든 보호 API 호출에 `Authorization: Bearer <token>` 첨부.
  - 토큰 없음 또는 401 응답 → **비밀번호 게이트 화면** 표시, 입력 성공 시 토큰 저장 후 본 화면.
- 보호 대상 엔드포인트: `/api/crawl`, `/api/crawl/stream`, `/api/export/sheet`, `/api/settings`(GET/POST), `/api/config/google-sheet`.
- 비보호: `/`(index.html), `/static/*`, `/healthz`, `/api/login`.
- 구현: FastAPI `Depends(require_token)` 의존성 하나를 보호 대상 라우트에 부착.
- 스트리밍 주의: `/api/crawl/stream`은 `EventSource`가 아니라 `fetch + getReader`(POST)로 호출되므로 `Authorization` 헤더 첨부에 제약 없음.

### 4.2 시트 URL 저장/조회

- 저장소: `engine/db.py`의 `EngineState`(key/value, `state.db`) 재사용.
- 헬퍼: `get_setting(session, key) -> str | None`, `set_setting(session, key, value)`.
- 키: `crawl_sheet_url`.
- `GET /api/settings` → `{ "sheet_url": str | null, "service_email": str | null }`
  - `service_email`은 `GoogleSheetExporter.get_service_email()` 재사용.
- `POST /api/settings {sheet_url}`:
  - URL 형식 검증(빈 값/형식 오류 → 400).
  - 시트 열기 검증: `GoogleSheetExporter`로 `open_by_url` 시도 → 실패 시 400 + "봇을 편집자로 초대했는지 확인" 안내.
  - 검증 통과 시 `crawl_sheet_url`에 저장.

### 4.3 자동 적재 흐름

- 프론트: 크롤링 완료(SSE `complete`) 수신 시,
  - 저장된 시트가 있으면(설정 로드로 확인) → 자동으로 `POST /api/export/sheet` 호출. body는 `companies`(+ keyword/source)만. **`sheet_url`은 보내지 않음** — 서버가 `state.db`에서 읽음.
  - 시트 미지정이면 → 자동 저장 스킵 + "먼저 설정에서 시트를 지정하세요" 안내 + 결과 화면에 수동 "지금 저장" 버튼 노출.
- 서버 `/api/export/sheet`:
  - `sheet_url`을 요청 body가 아닌 `state.db`에서 읽도록 변경. body의 `sheet_url`은 무시(또는 제거).
  - 저장 시트 없으면 400 + 안내.
- 결과는 화면에도 그대로 남아 있어 저장 실패해도 데이터 유실 없음.

### 4.4 UX 변화 정리

- 기존 "구글 시트" 모달(매번 URL 입력) → "설정" 화면으로 대체. 봇 이메일 초대 안내 + 시트 URL 1회 입력.
- 결과 화면: 자동 저장 결과를 토스트로 표시. 미지정 시 수동 "지금 저장" 버튼.
- 첫 접속: 비밀번호 게이트 → (선택) 설정에서 시트 지정 → 크롤링.

## 5. 에러 처리

| 상황 | 처리 |
|------|------|
| 비번 틀림 / 토큰 무효(401) | 게이트 화면 복귀, 재입력 요구 |
| 시트 미지정 상태에서 크롤 완료 | 자동 저장 스킵, 안내 + 수동 저장 버튼 |
| 시트 저장 실패(권한/잘못된 URL) | 명확한 토스트, 결과 화면 유지, 수동 재시도 |
| 설정 저장 시 시트 못 엶 | 저장 거부(400) + "봇 편집자 초대 확인" 안내 |
| `APP_PASSWORD` 미설정(배포) | README/주석 경고. 미설정 시 보호 비활성(개발용) |

## 6. 테스트 (TDD)

- `require_token`: 토큰 없음→401, 틀린 토큰→401, 맞는 토큰→통과.
- `get_setting`/`set_setting`: `state.db` 왕복 저장·조회.
- `GET/POST /api/settings`: 저장 후 조회 일치, 잘못된 URL → 400.
- `/api/export/sheet`: 서버 저장 URL 사용, 요청 body의 `sheet_url`은 무시. 시트 미지정 시 400.
- `/api/login`: 맞는/틀린 비밀번호.

## 7. 범위 밖 (Non-goals)

- 멀티유저/구글 OAuth 로그인.
- `engine/` 자동화 스케줄러의 control sheet와 통합(별도 시트로 둠).
- 자동 저장 on/off 토글.
- 크롤링 자체의 자동 트리거(크롤링은 여전히 수동 버튼).

## 8. 구현 순서(개략)

1. 접근 보호: `APP_PASSWORD`, `/api/login`, `require_token` 의존성, 프론트 게이트.
2. 설정 저장: `get_setting`/`set_setting`, `/api/settings` GET/POST, 프론트 설정 화면.
3. `/api/export/sheet`가 서버 저장 URL 사용하도록 변경.
4. 자동 적재: 크롤 완료 시 프론트 자동 export 호출.
5. 기존 "구글 시트" 모달 → 설정 화면으로 정리.
