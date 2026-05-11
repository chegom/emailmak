"""
Email Crawler API Server
FastAPI 기반 크롤링 API 서버
"""
import asyncio
import json
import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from crawlers import SaraminCrawler
from crawlers.jobkorea import JobKoreaCrawler
from crawlers.wanted import WantedCrawler
from utils.google_sheets import GoogleSheetExporter


app = FastAPI(
    title="Email Crawler API",
    description="사람인 등 채용사이트에서 회사 이메일을 크롤링하는 API",
    version="1.0.0"
)

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


class CrawlRequest(BaseModel):
    """크롤링 요청 모델"""
    keyword: str
    start_page: int = 1
    end_page: int = 5
    source: str = "saramin"  # 향후 확장용


class ExportRequest(BaseModel):
    """구글 시트 내보내기 요청 모델"""
    sheet_url: str
    companies: List[Dict[str, Any]]
    keyword: str = "검색어없음"
    source: str = "기타"


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
async def crawl(request: CrawlRequest):
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
async def crawl_stream(request: CrawlRequest):
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
async def export_sheet(request: ExportRequest):
    """구글 시트로 데이터 내보내기"""
    try:
        exporter = GoogleSheetExporter()
        success, message = exporter.export_to_sheet(
            request.sheet_url, 
            request.companies, 
            request.keyword, 
            request.source
        )
        
        if success:
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=500, detail=message)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/google-sheet")
async def get_google_sheet_config():
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
