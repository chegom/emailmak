"""
Saramin Crawler
사람인 채용사이트에서 회사 정보를 크롤링하는 모듈
"""
import asyncio
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urljoin

from .base import BaseCrawler
from .email_extractor import EmailExtractor


class SaraminCrawler(BaseCrawler):
    """사람인 크롤러"""
    
    BASE_URL = "https://www.saramin.co.kr"
    SEARCH_URL = "https://www.saramin.co.kr/zf_user/search"
    
    def __init__(self, timeout: float = 10.0):
        super().__init__(timeout)
        self.email_extractor = EmailExtractor(timeout=8.0)
    
    async def search(self, keyword: str, start_page: int = 1, end_page: int = 5) -> List[Dict[str, Any]]:
        """
        사람인에서 키워드 검색 후 회사 목록 반환
        
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
            print(f"[INFO] Crawling page {page} ({page - start_page + 1}/{total_pages})...")
            page_companies = await self._search_page(keyword, page)
            companies.extend(page_companies)
            
            # 요청 간 딜레이
            if page < end_page:
                await asyncio.sleep(0.5)
        
        # 중복 제거 (회사 URL 기준)
        seen = set()
        unique_companies = []
        for company in companies:
            if company['company_url'] and company['company_url'] not in seen:
                seen.add(company['company_url'])
                unique_companies.append(company)
        
        return unique_companies
    
    async def _search_page(self, keyword: str, page: int) -> List[Dict[str, Any]]:
        """단일 검색 페이지 크롤링"""
        params = {
            'search_area': 'main',
            'search_done': 'y',
            'search_optional_item': 'n',
            'searchType': 'search',
            'searchword': keyword,
            'recruitPage': str(page)
        }
        
        url = f"{self.SEARCH_URL}?{'&'.join(f'{k}={quote(str(v))}' for k, v in params.items())}"
        html = await self.fetch(url)
        
        if not html:
            return []
        
        return self._parse_search_results(html)
    
    def _parse_search_results(self, html: str) -> List[Dict[str, Any]]:
        """검색 결과 HTML 파싱"""
        soup = BeautifulSoup(html, 'lxml')
        companies = []
        
        # 채용공고 목록 찾기
        job_items = soup.select('.item_recruit')
        
        for item in job_items:
            try:
                # 회사명
                company_elem = item.select_one('.corp_name a')
                if not company_elem:
                    continue
                
                company_name = company_elem.get_text(strip=True)
                company_link = company_elem.get('href', '')
                
                # 회사 상세 페이지 URL
                if company_link and not company_link.startswith('http'):
                    company_link = urljoin(self.BASE_URL, company_link)
                
                # 채용 공고 제목
                job_elem = item.select_one('.job_tit a')
                job_title = job_elem.get_text(strip=True) if job_elem else ''
                
                companies.append({
                    'company_name': company_name,
                    'company_url': company_link,
                    'job_title': job_title,
                    'homepage': None,
                    'emails': []
                })
                
            except Exception as e:
                print(f"[WARN] Failed to parse item: {e}")
                continue
        
        return companies
    
    async def get_company_detail(self, company_url: str) -> Dict[str, Any]:
        """
        회사 상세 페이지에서 홈페이지 URL 추출
        
        Returns:
            {'homepage': 홈페이지 URL 또는 None}
        """
        html = await self.fetch(company_url)
        if not html:
            return {'homepage': None}
        
        soup = BeautifulSoup(html, 'lxml')
        
        # 회사 홈페이지 링크 찾기
        homepage = None
        
        # 방법 1: company_details_group 구조에서 홈페이지 찾기 (사람인 실제 구조)
        # <dt class="tit">홈페이지</dt> 다음의 <dd class="desc"><a href="...">
        dt_elements = soup.find_all('dt', class_='tit')
        for dt in dt_elements:
            if '홈페이지' in dt.get_text():
                # 다음 형제 요소(dd)에서 링크 찾기
                dd = dt.find_next_sibling('dd')
                if dd:
                    link = dd.find('a', href=True)
                    if link:
                        href = link.get('href', '')
                        if href.startswith('http') and 'saramin.co.kr' not in href:
                            homepage = href
                            break
        
        # 방법 2: dl.company_details a.ellipsis 셀렉터 사용
        if not homepage:
            link = soup.select_one('dl.company_details a.ellipsis')
            if link:
                href = link.get('href', '')
                if href.startswith('http') and 'saramin.co.kr' not in href:
                    homepage = href
        
        # 방법 3: 일반적인 외부 링크 탐색 (fallback)
        if not homepage:
            for link in soup.select('a[href^="http"]'):
                href = link.get('href', '')
                text = link.get_text(strip=True).lower()
                
                # 홈페이지 관련 텍스트 또는 회사 도메인 링크
                if any(kw in text for kw in ['홈페이지', '회사소개', 'homepage', 'website']):
                    if 'saramin.co.kr' not in href:
                        homepage = href
                        break
        
        # 방법 4: 기업정보 테이블에서 찾기 (fallback)
        if not homepage:
            info_items = soup.select('.info_item, .tb_col_list td, dd.desc')
            for item in info_items:
                link = item.find('a', href=True)
                if link:
                    href = link.get('href', '')
                    if href.startswith('http') and 'saramin.co.kr' not in href:
                        homepage = href
                        break
        
        print(f"[DEBUG] Found homepage for {company_url}: {homepage}")
        return {'homepage': homepage}
    
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
        
        print(f"[INFO] Found {total} companies (pages {start_page}-{end_page}). Extracting emails...")
        
        # 2. 각 회사별 홈페이지 및 이메일 추출
        for idx, company in enumerate(companies):
            try:
                if progress_callback:
                    progress_callback(idx + 1, total, company['company_name'])
                
                # 회사 상세 페이지에서 홈페이지 URL 가져오기
                if company['company_url']:
                    detail = await self.get_company_detail(company['company_url'])
                    company['homepage'] = detail.get('homepage')
                
                # 홈페이지에서 이메일 추출
                if company['homepage']:
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
