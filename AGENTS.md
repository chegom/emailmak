<claude-mem-context>
# Memory Context

# [emailmak-main] recent context, 2026-05-11 2:57pm GMT+9

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 2 obs (578t read) | 24,560t work | 98% savings

### May 11, 2026
S1670 Code review requested via /code-review skill — awaiting PR reference (May 11 at 2:40 PM)
2362 2:41p 🔵 emailmak-main — 코드 리뷰 중 발견된 주요 버그 및 설계 문제 5건
2363 " 🔵 emailmak-main 크롤러 아키텍처 — WantedCrawler.crawl_with_emails() 누락으로 런타임 크래시 확실
S1671 emailmak-main 전체 코드베이스 코드 리뷰 — 6건의 기능/보안 이슈 발견 및 보고 완료 (May 11 at 2:42 PM)
**Investigated**: server.py, crawlers/base.py, crawlers/saramin.py, crawlers/jobkorea.py, crawlers/wanted.py, crawlers/email_extractor.py, utils/google_sheets.py, requirements.txt, README.md, Procfile, railway.json 전체 파일 검토

**Learned**: - emailmak-main은 사람인·잡코리아·원티드 3개 채용사이트에서 기업 이메일을 크롤링하는 FastAPI 서버로 Railway에 배포됨
    - /api/export/sheet 라우트가 server.py에 두 번 정의되어 첫 번째가 데드코드
    - CORS allow_origins=["*"] + allow_credentials=True 조합은 브라우저 스펙상 무효
    - BaseCrawler.search() ABC 시그니처(pages=5)와 구현체 시그니처(start_page, end_page) 불일치
    - README 포트 8000, __main__ 포트 8001, Procfile $PORT — 3곳이 불일치하여 로컬 실행 안내 오류
    - /api/debug/jobkorea 엔드포인트가 인증 없이 프로덕션에 노출
    - EmailExtractor가 verify=False로 전체 SSL 검증 비활성화
    - WantedCrawler.crawl_with_emails() 미구현 — /api/crawl에서 wanted 선택 시 AttributeError 런타임 크래시
    - WantedCrawler.fetch_json()이 매 호출마다 새 httpx.AsyncClient 생성
    - /api/crawl/stream이 /api/crawl과 달리 페이지 범위 검증 누락

**Completed**: 전체 코드베이스 코드 리뷰 완료. 기능/보안 영향이 큰 6건 + 자잘한 사항 3건을 정리하여 사용자에게 보고 완료. 코드 수정은 수행하지 않음 — 리뷰 결과 전달만 완료.

**Next Steps**: 코드 리뷰 결과를 바탕으로 사용자가 수정 작업을 요청할 경우 수정 진행 예정. 현재는 리뷰 결과 확인 대기 상태.


Access 25k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>