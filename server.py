"""
Email Crawler API Server
FastAPI 기반 크롤링 API 서버
"""
import asyncio
import json
import os
from typing import Optional, List, Dict, Any, Generator
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from crawlers import SaraminCrawler
from crawlers.jobkorea import JobKoreaCrawler
from crawlers.wanted import WantedCrawler
from engine.db import Base as EngineBase
from engine.db import SessionLocal as EngineSessionLocal
from engine.db import engine as engine_state_engine
import engine.models  # noqa: F401
from engine.scheduler import acquire_lock, clear_stale_locks, due_rows, lock_key, release_lock
from engine.kv import get_setting, set_setting
from utils.google_sheets import GoogleSheetExporter

import auth


app = FastAPI(
    title="Email Crawler API",
    description="사람인 등 채용사이트에서 회사 이메일을 크롤링하는 API",
    version="1.0.0"
)

_engine_scheduler = None


def ensure_state_schema():
    """Create the engine state.db tables. Must run regardless of ENGINE_ENABLED,
    because the crawl settings/export endpoints depend on the engine_state table."""
    EngineBase.metadata.create_all(engine_state_engine)


@app.on_event("startup")
async def _ensure_state_schema():
    ensure_state_schema()


@app.on_event("startup")
async def _start_engine():
    """Start the sheet-driven automation scheduler when engine env is configured."""
    global _engine_scheduler
    if os.getenv("ENGINE_ENABLED", "1") != "1":
        return

    try:
        from datetime import datetime, timedelta
        from engine.settings import get_engine_settings

        get_engine_settings()
        ensure_state_schema()
        with EngineSessionLocal() as session:
            clear_stale_locks(session, before=datetime.utcnow() - timedelta(hours=6))

        _engine_scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
        _engine_scheduler.add_job(
            _run_tick,
            "interval",
            hours=1,
            max_instances=1,
            coalesce=True,
            id="hourly_tick",
        )
        _engine_scheduler.start()
    except Exception as exc:
        print(f"[WARN] Engine scheduler not started: {exc}")


@app.on_event("shutdown")
async def _stop_engine():
    global _engine_scheduler
    if _engine_scheduler:
        _engine_scheduler.shutdown(wait=False)
        _engine_scheduler = None


@app.get("/healthz")
async def healthz():
    ok = True
    try:
        with EngineSessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        ok = False
    return {"ok": ok}


async def _run_tick():
    from datetime import datetime

    from engine.alerts import AlertMonitor
    from engine.crawler_service import CrawlerService
    from engine.dedup import DedupStore
    from engine.gemini import GeminiClient
    from engine.keywords import KeywordResolver
    from engine.pipeline import RunPipeline
    from engine.planner import SchedulePlanner
    from engine.settings import get_engine_settings
    from engine.sheets import SheetControl, open_control_sheet
    from engine.smartlead import SmartleadClient
    from engine.validator import EmailValidator

    cfg = get_engine_settings()
    spreadsheet = open_control_sheet(cfg.google_credentials_json, cfg.control_sheet_url)
    sheet = SheetControl(spreadsheet)
    gemini = GeminiClient(api_key=cfg.gemini_api_key)
    resolver = KeywordResolver(gemini=gemini)
    smartlead = SmartleadClient(api_key=cfg.smartlead_api_key)

    settings = sheet.read_settings()
    SchedulePlanner(sheet, resolver).topup(settings)

    now = datetime.now()
    run_id = now.strftime("%Y%m%d%H%M")
    by_industry = {job.industry: job for job in settings}

    for row in due_rows(sheet.read_schedule(), now):
        job = by_industry.get(row.industry)
        if not job:
            continue

        key = lock_key(row)
        with EngineSessionLocal() as session:
            if not acquire_lock(session, key):
                continue

        try:
            if not row.keyword:
                keywords, source = resolver.resolve(
                    industry=job.industry,
                    manual="",
                    avoid=[],
                    n=job.topup_count,
                )
                row.keyword = ", ".join(keywords)
                sheet.set_schedule_keyword(row.row_number, row.keyword, source)

            with EngineSessionLocal() as session:
                alert = AlertMonitor(
                    session,
                    smartlead,
                    sheet,
                    warn=cfg.bounce_warn,
                    critical=cfg.bounce_critical,
                    min_sample=cfg.min_bounce_sample,
                )
                pipeline = RunPipeline(
                    session=session,
                    crawler=CrawlerService(),
                    validator=EmailValidator(session),
                    dedup=DedupStore(session),
                    smartlead=smartlead,
                    sheet=sheet,
                    alert=alert,
                    min_pass_rate=cfg.min_pass_rate,
                )
                await pipeline.run_row(run_id=run_id, row=row, job=job)
        finally:
            with EngineSessionLocal() as session:
                release_lock(session, key)

    with EngineSessionLocal() as session:
        alert = AlertMonitor(
            session,
            smartlead,
            sheet,
            warn=cfg.bounce_warn,
            critical=cfg.bounce_critical,
            min_sample=cfg.min_bounce_sample,
        )
        alert.poll_bounce(run_id=run_id, campaign_ids=list({job.campaign_id for job in settings}))

def _get_cors_origins() -> List[str]:
    origins = os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000"
    )
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


CORS_ALLOW_ORIGINS = _get_cors_origins()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials="*" not in CORS_ALLOW_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_session() -> Generator[Session, None, None]:
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
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="시트를 열 수 없습니다. 봇 계정을 편집자로 초대했는지 확인하세요.",
        )
    set_setting(session, "crawl_sheet_url", url)
    session.commit()
    return {"success": True, "sheet_url": url}


class CrawlRequest(BaseModel):
    """크롤링 요청 모델"""
    keyword: str
    start_page: int = 1
    end_page: int = 5
    source: str = "saramin"  # 향후 확장용


class ExportRequest(BaseModel):
    """구글 시트 내보내기 요청 모델 (sheet_url은 무시됨 — 서버 저장값 사용)"""
    companies: List[Dict[str, Any]]
    keyword: str = "검색어없음"
    source: str = "기타"
    sheet_url: Optional[str] = None  # 하위 호환용, 사용 안 함


class CompanyResult(BaseModel):
    """회사 결과 모델"""
    company_name: str
    company_url: Optional[str] = None
    job_title: Optional[str] = None
    homepage: Optional[str] = None
    emails: list = []


CRAWLER_CLASSES = {
    "saramin": SaraminCrawler,
    "jobkorea": JobKoreaCrawler,
    "wanted": WantedCrawler,
}


def validate_crawl_request(request: CrawlRequest):
    if not request.keyword.strip():
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")

    if request.start_page < 1 or request.end_page < 1:
        raise HTTPException(status_code=400, detail="페이지 번호는 1 이상이어야 합니다.")

    if request.start_page > request.end_page:
        raise HTTPException(status_code=400, detail="시작 페이지는 끝 페이지보다 작거나 같아야 합니다.")


def get_crawler_class(source: str):
    crawler_class = CRAWLER_CLASSES.get(source)
    if not crawler_class:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 소스: {source}")
    return crawler_class


@app.post("/api/crawl")
async def crawl(request: CrawlRequest, _=Depends(require_token)):
    """
    크롤링 API (일반 JSON 응답)
    """
    validate_crawl_request(request)
    
    try:
        crawler_class = get_crawler_class(request.source)
        
        async with crawler_class() as crawler:
            results = await crawler.crawl_with_emails(
                keyword=request.keyword,
                start_page=request.start_page,
                end_page=request.end_page
            )
            return {
                "success": True,
                "keyword": request.keyword,
                "source": request.source,
                "total": len(results),
                "companies": results
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crawl/stream")
async def crawl_stream(request: CrawlRequest, _=Depends(require_token)):
    """
    크롤링 API (SSE 스트리밍 응답)
    실시간으로 진행 상황을 전송
    """
    validate_crawl_request(request)
    crawler_class = get_crawler_class(request.source)
    
    async def generate():
        try:
            async with crawler_class() as crawler:
                # 검색 결과 먼저 전송
                companies = await crawler.search(request.keyword, request.start_page, request.end_page)
                total = len(companies)
                
                yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"
                
                # 각 회사별 이메일 추출
                for idx, company in enumerate(companies):
                    try:
                        # 소스 정보 추가 (프론트엔드에서 링크 라벨 결정에 사용)
                        company['source'] = request.source
                        
                        # 잡코리아의 경우: job_url에서 company_url 추출
                        if request.source == 'jobkorea' and company.get('job_url') and not company.get('company_url'):
                            company_url = await crawler._get_company_url_from_job(company['job_url'])
                            company['company_url'] = company_url
                        
                        # 회사 상세 페이지에서 홈페이지 URL
                        if company.get('company_url'):
                            detail = await crawler.get_company_detail(company['company_url'])
                            company['homepage'] = detail.get('homepage')
                        
                        # 홈페이지에서 이메일 추출
                        if company.get('homepage'):
                            emails = await crawler.email_extractor.extract_from_url(company['homepage'])
                            company['emails'] = emails
                        
                        # 진행 상황 전송
                        yield f"data: {json.dumps({'type': 'progress', 'current': idx + 1, 'total': total, 'company': company}, ensure_ascii=False)}\n\n"
                        
                        await asyncio.sleep(0.3)
                        
                    except Exception as e:
                        error_msg = f"[ERROR] {company.get('company_name', 'Unknown')}: {type(e).__name__}: {e}"
                        print(error_msg)
                        company['error'] = str(e)  # 에러 정보를 company에 추가
                        yield f"data: {json.dumps({'type': 'progress', 'current': idx + 1, 'total': total, 'company': company}, ensure_ascii=False)}\n\n"
                
                # 완료 메시지
                yield f"data: {json.dumps({'type': 'complete', 'total': total})}\n\n"
                
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


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


@app.get("/api/config/google-sheet")
async def get_google_sheet_config(_=Depends(require_token)):
    """구글 시트 설정 정보(봇 이메일) 반환"""
    try:
        exporter = GoogleSheetExporter()
        email = exporter.get_service_email()
        return {"service_email": email}
    except Exception:
        return {"service_email": None}


# 정적 파일 서빙
@app.get("/")
async def root():
    return FileResponse("static/index.html")


# 정적 파일 마운트 (index.html 이후에)
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
