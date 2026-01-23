"""
Wanted Crawler
원티드(Wanted) 채용 사이트에서 회사 정보를 크롤링하는 모듈
API를 직접 호출하여 빠르고 정확하게 데이터를 수집합니다.
"""
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import quote

from .base import BaseCrawler
from .email_extractor import EmailExtractor


class WantedCrawler(BaseCrawler):
    """원티드 크롤러"""
    
    BASE_URL = "https://www.wanted.co.kr"
    API_SEARCH_URL = "https://www.wanted.co.kr/api/v4/search"
    API_COMPANY_URL = "https://www.wanted.co.kr/api/v4/companies"
    
    def __init__(self, timeout: float = 15.0):
        super().__init__(timeout)
        self.email_extractor = EmailExtractor(timeout=10.0)
    
    async def search(self, keyword: str, start_page: int = 1, end_page: int = 5) -> List[Dict[str, Any]]:
        """
        원티드에서 키워드 검색 후 회사 목록 반환
        원티드 API는 페이지네이션 대신 무한 스크롤 방식을 사용하지만, 
        검색 API에서는 한 번에 일정 개수의 결과를 반환합니다.
        
        Args:
            keyword: 검색 키워드
            start_page: 시작 페이지 (원티드 검색 API는 페이지 개념이 명확하지 않아 offset 등을 고려해야 할 수도 있음)
            end_page: 끝 페이지
        
        Returns:
            회사 정보 리스트
        """
        companies = []
        
        # 원티드 검색 API 호출
        # 참고: 원티드 API는 limit/offset을 사용할 수 있으나, v4/search 기본 호출은 상위 결과를 반환함
        # 여기서는 가장 정확도가 높은 상위 결과들을 가져옴
        
        print(f"[INFO] Searching Wanted for '{keyword}'...")
        
        try:
            # 검색 API 호출
            url = f"{self.API_SEARCH_URL}?query={quote(keyword)}&tab=company&country=kr&locations=all"
            data = await self.fetch_json(url)
            
            if not data or 'data' not in data or 'companies' not in data['data']:
                print("[WARN] No data found in Wanted search response")
                return []
            
            raw_companies = data['data']['companies']
            print(f"[INFO] Found {len(raw_companies)} companies in Wanted search")
            
            # 페이지네이션 흉내내기 (결과가 많을 경우 슬라이싱)
            # 원티드 검색 API가 한 번에 100개까지도 줄 수 있다면, 
            # start_page, end_page로 슬라이싱하여 반환하는 것이 합리적일 수 있음
            # 일단 전체 결과를 다 가져와서 처리
            
            for item in raw_companies:
                try:
                    company_id = item.get('id')
                    company_name = item.get('name')
                    
                    if not company_id or not company_name:
                        continue
                        
                    company_url = f"{self.BASE_URL}/company/{company_id}"
                    
                    # API용 ID 저장 (상세 정보 조회시 사용)
                    api_id = company_id
                    
                    companies.append({
                        'company_name': company_name,
                        'company_url': company_url,
                        'api_id': api_id, # 내부용 ID
                        'job_url': None, # 원티드는 회사 중심이므로 채용공고 URL은 선택적
                        'job_title': f"{company_name} 채용 정보", # 임시 제목
                        'homepage': None,
                        'emails': []
                    })
                    
                except Exception as e:
                    print(f"[WARN] Failed to parse Wanted company item: {e}")
                    continue
            
            # 페이지네이션 적용 (간단하게 리스트 슬라이싱으로 구현)
            # 보통 한 페이지당 10-20개라고 가정
            items_per_page = 10
            start_idx = (start_page - 1) * items_per_page
            end_idx = end_page * items_per_page
            
            return companies[start_idx:end_idx]
            
        except Exception as e:
            print(f"[ERROR] Wanted search failed: {e}")
            return []
    
    async def get_company_detail(self, company_url_or_id: str) -> Dict[str, Any]:
        """
        회사 상세 정보(홈페이지 URL) 조회
        
        Args:
            company_url_or_id: 회사 URL 또는 API ID
            
        Returns:
            {'homepage': 홈페이지 URL 또는 None}
        """
        try:
            # URL에서 ID 추출 또는 ID 그대로 사용
            api_id_str = str(company_url_or_id)
            if api_id_str.isdigit():
                api_id = api_id_str
            else:
                # URL 형태: https://www.wanted.co.kr/company/12345
                parts = api_id_str.rstrip('/').split('/')
                api_id = parts[-1]
                
            if not str(api_id).isdigit():
                print(f"[WARN] Invalid Wanted company ID/URL: {company_url_or_id}")
                return {'homepage': None}
                
            url = f"{self.API_COMPANY_URL}/{api_id}"
            print(f"[DEBUG] Fetching Wanted company detail: {url}")
            
            data = await self.fetch_json(url)
            
            if not data or 'company' not in data or 'detail' not in data['company']:
                return {'homepage': None}
            
            detail = data['company']['detail']
            homepage = detail.get('link')
            
            # 홈페이지 URL 정리
            if homepage:
                # http/https가 없으면 붙여줌
                if not homepage.startswith('http'):
                    homepage = f"http://{homepage}"
                
                print(f"[DEBUG] Found homepage for company {api_id}: {homepage}")
            
            return {'homepage': homepage}
            
        except Exception as e:
            print(f"[ERROR] Failed to get Wanted company detail: {e}")
            return {'homepage': None}
    
    async def fetch_json(self, url: str) -> Optional[Dict[str, Any]]:
        """JSON 데이터 가져오기"""
        import httpx
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://www.wanted.co.kr/'
            }
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"[WARN] API request failed with status {response.status_code}: {url}")
                    return None
        except Exception as e:
            print(f"[ERROR] API request error: {e}")
            return None
