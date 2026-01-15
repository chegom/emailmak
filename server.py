"""
Email Crawler API Server
FastAPI 기반 크롤링 API 서버
"""
import asyncio
import json
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from crawlers import SaraminCrawler


app = FastAPI(
    title="Email Crawler API",
    description="사람인 등 채용사이트에서 회사 이메일을 크롤링하는 API",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CrawlRequest(BaseModel):
    """크롤링 요청 모델"""
    keyword: str
    pages: int = 5
    source: str = "saramin"  # 향후 확장용


class CompanyResult(BaseModel):
    """회사 결과 모델"""
    company_name: str
    company_url: Optional[str] = None
    job_title: Optional[str] = None
    homepage: Optional[str] = None
    emails: list = []


@app.post("/api/crawl")
async def crawl(request: CrawlRequest):
    """
    크롤링 API (일반 JSON 응답)
    """
    if not request.keyword.strip():
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")
    
    if request.pages < 1 or request.pages > 10:
        raise HTTPException(status_code=400, detail="페이지 수는 1~10 사이여야 합니다.")
    
    try:
        if request.source == "saramin":
            async with SaraminCrawler() as crawler:
                results = await crawler.crawl_with_emails(
                    keyword=request.keyword,
                    pages=request.pages
                )
                return {
                    "success": True,
                    "keyword": request.keyword,
                    "total": len(results),
                    "companies": results
                }
        else:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 소스: {request.source}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/crawl/stream")
async def crawl_stream(request: CrawlRequest):
    """
    크롤링 API (SSE 스트리밍 응답)
    실시간으로 진행 상황을 전송
    """
    if not request.keyword.strip():
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")
    
    async def generate():
        try:
            if request.source == "saramin":
                async with SaraminCrawler() as crawler:
                    # 검색 결과 먼저 전송
                    companies = await crawler.search(request.keyword, request.pages)
                    total = len(companies)
                    
                    yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"
                    
                    # 각 회사별 이메일 추출
                    for idx, company in enumerate(companies):
                        try:
                            # 회사 상세 페이지에서 홈페이지 URL
                            if company['company_url']:
                                detail = await crawler.get_company_detail(company['company_url'])
                                company['homepage'] = detail.get('homepage')
                            
                            # 홈페이지에서 이메일 추출
                            if company['homepage']:
                                emails = await crawler.email_extractor.extract_from_url(company['homepage'])
                                company['emails'] = emails
                            
                            # 진행 상황 전송
                            yield f"data: {json.dumps({'type': 'progress', 'current': idx + 1, 'total': total, 'company': company}, ensure_ascii=False)}\n\n"
                            
                            await asyncio.sleep(0.3)
                            
                        except Exception as e:
                            print(f"[ERROR] {company['company_name']}: {e}")
                            yield f"data: {json.dumps({'type': 'progress', 'current': idx + 1, 'total': total, 'company': company}, ensure_ascii=False)}\n\n"
                    
                    # 완료 메시지
                    yield f"data: {json.dumps({'type': 'complete', 'total': total})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': f'지원하지 않는 소스: {request.source}'})}\n\n"
                
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


# 정적 파일 서빙
@app.get("/")
async def root():
    return FileResponse("static/index.html")


# 정적 파일 마운트 (index.html 이후에)
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
