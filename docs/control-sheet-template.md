# Control Sheet Template

Create one Google Sheet and share it with the crawler service account as an editor.

The spreadsheet must contain these four tabs with exactly these header rows.

## ⚙️설정

| 산업군 | 사이트 | 캠페인ID | 주기(일) | 미리채울회수 | 페이지 | 활성화 |
|---|---|---|---|---|---|---|
| 물류 | saramin,jobkorea,wanted | 123456 | 3 | 5 | 1-5 | Y |

## 📅키워드스케줄

| 예정일시 | 산업군 | 키워드 | 출처 | 상태 |
|---|---|---|---|---|
| 2026-06-04 09:00 | 물류 | 3PL, 풀필먼트 | manual | 예정 |

`예정일시` may be `YYYY-MM-DD HH:MM` or `YYYY-MM-DD`. Date-only values run at 09:00 Asia/Seoul.

## 발송내역

| 기록일시 | 실행ID | 회사명 | 이메일 | 산업군 | 키워드 | 사이트 | 캠페인ID | 검증결과 | 역할주소여부 | push_status | accepted_at | 응답요약 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

Only `push_status=accepted` rows should be used for dedup backfill.

## ⚠️경고

| 일시 | 실행ID | 종류 | 상세 | 수치 |
|---|---|---|---|---|

## Railway Environment

Set these variables:

- `SMARTLEAD_API_KEY`
- `GEMINI_API_KEY`
- `CONTROL_SHEET_URL`
- `GOOGLE_CREDENTIALS_JSON`
- `STATE_DB_URL=sqlite:////data/state.db`

Optional thresholds:

- `BOUNCE_WARN=0.05`
- `BOUNCE_CRITICAL=0.08`
- `MIN_PASS_RATE=0.40`
- `SMARTLEAD_DAILY_LIMIT=200`

Add a Railway volume mounted at `/data` so `state.db` survives restarts.
