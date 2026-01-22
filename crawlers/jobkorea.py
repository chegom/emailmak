"""
JobKorea Crawler
잡코리아 채용사이트에서 회사 정보를 크롤링하는 모듈
"""
import asyncio
import re
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urljoin

from .base import BaseCrawler
from .email_extractor import EmailExtractor


class JobKoreaCrawler(BaseCrawler):
    """잡코리아 크롤러"""
    
    BASE_URL = "https://www.jobkorea.co.kr"
    SEARCH_URL = "https://www.jobkorea.co.kr/Search/"
    
    def __init__(self, timeout: float = 15.0):
        super().__init__(timeout)
        self.email_extractor = EmailExtractor(timeout=10.0)
    
    async def search(self, keyword: str, start_page: int = 1, end_page: int = 5) -> List[Dict[str, Any]]:
        """
        잡코리아에서 키워드 검색 후 회사 목록 반환
        
        Args:
            keyword: 검색 키워드
            start_page: 시작 페이지 (기본 1)
            end_page: 끝 페이지 (기본 5)
        
        Returns:
            회사 정보 리스트 [{company_name, company_url, job_title}, ...]
        """
        companies = []
        total_pages = end_page - start_page + 1
        
        for page in range(start_page, end_page + 1):
            print(f"[INFO] Crawling JobKorea page {page} ({page - start_page + 1}/{total_pages})...")
            page_companies = await self._search_page(keyword, page)
            companies.extend(page_companies)
            
            # 요청 간 딜레이
            if page < end_page:
                await asyncio.sleep(0.5)
        
        # 중복 제거 (회사명 기준)
        seen = set()
        unique_companies = []
        for company in companies:
            company_key = company['company_name']
            if company_key and company_key not in seen:
                seen.add(company_key)
                unique_companies.append(company)
        
        return unique_companies
    
    async def _search_page(self, keyword: str, page: int) -> List[Dict[str, Any]]:
        """단일 검색 페이지 크롤링"""
        url = f"{self.SEARCH_URL}?stext={quote(keyword)}&Page_No={page}"
        html = await self.fetch(url)
        
        if not html:
            return []
        
        return self._parse_search_results(html)
    
    def _parse_search_results(self, html: str) -> List[Dict[str, Any]]:
        """검색 결과 HTML 파싱 - 새로운 잡코리아 UI 구조"""
        soup = BeautifulSoup(html, 'lxml')
        companies = []
        seen_companies = set()
        
        # 새로운 UI: Box_bgColor_white + Box_borderColor를 가진 채용공고 카드 찾기
        job_cards = soup.select('div[class*="Box_bgColor_white"][class*="Box_borderColor"]')
        
        for card in job_cards:
            try:
                # 카드 내 모든 GI_Read 링크 가져오기
                links = card.select('a[href*="/Recruit/GI_Read/"]')
                
                if len(links) < 2:
                    continue
                
                # 채용공고 URL (첫 번째 링크의 href)
                job_url = links[0].get('href', '')
                if job_url and not job_url.startswith('http'):
                    job_url = urljoin(self.BASE_URL, job_url)
                
                # 텍스트가 있는 링크들 추출
                text_links = [(link.get_text(strip=True), link) for link in links if link.get_text(strip=True)]
                
                if len(text_links) < 2:
                    continue
                
                # 텍스트 길이로 정렬 (긴 것이 채용 제목, 짧은 것이 회사명)
                text_links.sort(key=lambda x: len(x[0]), reverse=True)
                job_title = text_links[0][0]  # 가장 긴 텍스트 = 채용 제목
                company_name = text_links[-1][0]  # 가장 짧은 텍스트 = 회사명
                
                if not company_name or company_name in seen_companies:
                    continue
                
                seen_companies.add(company_name)
                
                companies.append({
                    'company_name': company_name,
                    'company_url': None,  # 나중에 GI_Read 페이지에서 Co_Read URL 추출
                    'job_url': job_url,
                    'job_title': job_title,
                    'homepage': None,
                    'emails': []
                })
                
            except Exception as e:
                print(f"[WARN] Failed to parse job card: {e}")
                continue
        
        return companies
    
    async def get_company_detail(self, company_url: str) -> Dict[str, Any]:
        """
        회사 상세 페이지(Co_Read)에서 홈페이지 URL 추출
        
        Args:
            company_url: 회사 상세 페이지 URL (Co_Read/C/{id})
        
        Returns:
            {'homepage': 홈페이지 URL 또는 None}
        """
        html = await self.fetch(company_url)
        if not html:
            return {'homepage': None}
        
        soup = BeautifulSoup(html, 'lxml')
        
        homepage = None
        
        # 제외할 도메인 목록
        exclude_domains = [
            'jobkorea.co.kr', 'albamon.com', 'gamejob.co.kr', 'ninehire.com',
            'klik.co.kr', 'naver.com', 'facebook.com', 'instagram.com', 
            'youtube.com', 'notion.site', 'oopy.io', 'google.com', 
            'daum.net', 'kakao.com', 'nicebizinfo.com', 'dataline.co.kr'
        ]
        
        # 방법 1: 홈페이지 텍스트가 있는 링크 찾기
        for elem in soup.find_all(string=lambda t: t and '홈페이지' in t):
            parent = elem.parent
            next_link = parent.find_next('a', href=True)
            if next_link:
                href = next_link.get('href', '')
                if href.startswith('http') and not any(d in href for d in exclude_domains):
                    homepage = href
                    break
        
        # 방법 2: 외부 링크 중 첫 번째 유효한 링크
        if not homepage:
            for link in soup.select('a[href^="http"]'):
                href = link.get('href', '')
                if not any(d in href for d in exclude_domains):
                    homepage = href
                    break
        
        print(f"[DEBUG] JobKorea found homepage: {homepage}")
        return {'homepage': homepage}
    
    async def _get_company_url_from_job(self, job_url: str) -> Optional[str]:
        """
        채용공고 페이지(GI_Read)에서 회사 상세 페이지(Co_Read) URL 추출
        
        Args:
            job_url: 채용공고 URL (GI_Read/{id})
        
        Returns:
            회사 상세 페이지 URL 또는 None
        """
        print(f"[DEBUG] Fetching job page: {job_url}")
        html = await self.fetch(job_url)
        if not html:
            print(f"[DEBUG] Failed to fetch job page: {job_url}")
            return None
        
        print(f"[DEBUG] Job page fetched, length: {len(html)}")
        
        # Co_Read URL 패턴 찾기
        co_read_pattern = r'/Recruit/Co_Read/C/(\d+)'
        match = re.search(co_read_pattern, html)
        
        if match:
            company_id = match.group(1)
            company_url = f"{self.BASE_URL}/Recruit/Co_Read/C/{company_id}"
            print(f"[DEBUG] Found company URL: {company_url}")
            return company_url
        
        print(f"[DEBUG] Co_Read pattern not found in job page")
        return None
    
    async def crawl_with_emails(self, keyword: str, start_page: int = 1, end_page: int = 5, 
                                 progress_callback=None) -> List[Dict[str, Any]]:
        """
        검색부터 이메일 추출까지 전체 크롤링
        
        Args:
            keyword: 검색 키워드
            start_page: 시작 페이지
            end_page: 끝 페이지
            progress_callback: 진행 상황 콜백 함수 (current, total, company_name)
        
        Returns:
            완성된 회사 정보 리스트
        """
        # 1. 검색 결과 수집
        companies = await self.search(keyword, start_page, end_page)
        total = len(companies)
        
        print(f"[INFO] JobKorea found {total} companies (pages {start_page}-{end_page}). Extracting details...")
        
        # 2. 각 회사별 홈페이지 및 이메일 추출
        for idx, company in enumerate(companies):
            try:
                if progress_callback:
                    progress_callback(idx + 1, total, company['company_name'])
                
                # 채용공고 페이지에서 회사 상세 페이지 URL 가져오기
                if company.get('job_url'):
                    company_url = await self._get_company_url_from_job(company['job_url'])
                    company['company_url'] = company_url
                    
                    # 회사 상세 페이지에서 홈페이지 URL 가져오기
                    if company_url:
                        detail = await self.get_company_detail(company_url)
                        company['homepage'] = detail.get('homepage')
                
                # 홈페이지에서 이메일 추출
                if company.get('homepage'):
                    emails = await self.email_extractor.extract_from_url(company['homepage'])
                    company['emails'] = emails
                
                # 요청 간 딜레이
                await asyncio.sleep(0.3)
                
            except Exception as e:
                print(f"[ERROR] Failed to process {company['company_name']}: {e}")
                continue
        
        # 이메일이 있는 회사만 우선 정렬
        companies.sort(key=lambda x: len(x.get('emails', [])), reverse=True)
        
        return companies
