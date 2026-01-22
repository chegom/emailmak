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
from crawlers.jobkorea import JobKoreaCrawler


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
    start_page: int = 1
    end_page: int = 5
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
    
    if request.start_page < 1 or request.end_page < 1:
        raise HTTPException(status_code=400, detail="페이지 번호는 1 이상이어야 합니다.")
    
    if request.start_page > request.end_page:
        raise HTTPException(status_code=400, detail="시작 페이지는 끝 페이지보다 작거나 같아야 합니다.")
    
    try:
        # 소스에 따른 크롤러 선택
        if request.source == "saramin":
            crawler_class = SaraminCrawler
        elif request.source == "jobkorea":
            crawler_class = JobKoreaCrawler
        else:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 소스: {request.source}")
        
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
            # 소스에 따른 크롤러 선택
            if request.source == "saramin":
                crawler_class = SaraminCrawler
            elif request.source == "jobkorea":
                crawler_class = JobKoreaCrawler
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': f'지원하지 않는 소스: {request.source}'})}\n\n"
                return
            
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


# 디버그 엔드포인트 - JobKorea 크롤링 진단용
@app.get("/api/debug/jobkorea")
async def debug_jobkorea(keyword: str = "개발자"):
    """JobKorea 크롤링 디버그 - Railway 환경 테스트용"""
    from urllib.parse import quote
    import httpx
    import re
    
    results = {
        "keyword": keyword,
        "search_url": None,
        "search_response": {
            "status_code": None,
            "content_length": 0,
            "has_job_cards": False,
            "job_card_count": 0,
        },
        "parsed_companies": [],
        "detail_test": {
            "job_url": None,
            "job_page_status": None,
            "job_page_length": 0,
            "co_read_pattern_found": False,
            "company_url": None,
            "company_page_status": None,
            "company_page_length": 0,
            "homepage_found": None,
        },
        "errors": []
    }
    
    try:
        search_url = f"https://www.jobkorea.co.kr/Search/?stext={quote(keyword)}&Page_No=1"
        results["search_url"] = search_url
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
            response = await client.get(search_url)
            results["search_response"]["status_code"] = response.status_code
            results["search_response"]["content_length"] = len(response.text)
            
            # Job cards 확인
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'lxml')
            
            job_cards = soup.select('div[class*="Box_bgColor_white"][class*="Box_borderColor"]')
            results["search_response"]["has_job_cards"] = len(job_cards) > 0
            results["search_response"]["job_card_count"] = len(job_cards)
            
            # 실제 크롤러로 파싱 테스트
            async with JobKoreaCrawler() as crawler:
                companies = await crawler.search(keyword, 1, 1)
                results["parsed_companies"] = companies[:3]  # 최대 3개만
                
                # 첫 번째 회사의 상세 정보 추출 테스트
                if companies and companies[0].get('job_url'):
                    job_url = companies[0]['job_url']
                    results["detail_test"]["job_url"] = job_url
                    
                    # 1. 채용공고 페이지에서 회사URL 추출 테스트
                    job_response = await client.get(job_url)
                    results["detail_test"]["job_page_status"] = job_response.status_code
                    results["detail_test"]["job_page_length"] = len(job_response.text)
                    
                    # Co_Read 패턴 찾기
                    co_read_pattern = r'/Recruit/Co_Read/C/(\d+)'
                    match = re.search(co_read_pattern, job_response.text)
                    results["detail_test"]["co_read_pattern_found"] = match is not None
                    
                    if match:
                        company_id = match.group(1)
                        company_url = f"https://www.jobkorea.co.kr/Recruit/Co_Read/C/{company_id}"
                        results["detail_test"]["company_url"] = company_url
                        
                        # 2. 회사 상세 페이지에서 홈페이지 URL 추출 테스트
                        company_response = await client.get(company_url)
                        results["detail_test"]["company_page_status"] = company_response.status_code
                        results["detail_test"]["company_page_length"] = len(company_response.text)
                        
                        # 홈페이지 URL 찾기 (크롤러 로직과 동일)
                        detail = await crawler.get_company_detail(company_url)
                        results["detail_test"]["homepage_found"] = detail.get('homepage')
            
    except Exception as e:
        results["errors"].append(str(e))
    
    return results


# 정적 파일 서빙
@app.get("/")
async def root():
    return FileResponse("static/index.html")


# 정적 파일 마운트 (index.html 이후에)
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
