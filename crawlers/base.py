"""
Base Crawler Class
확장 가능한 크롤러 베이스 클래스
"""
import re
import httpx
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseCrawler(ABC):
    """크롤러 베이스 클래스"""
    
    # 공통 헤더
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    # 이메일 추출 정규식
    EMAIL_PATTERN = re.compile(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        re.IGNORECASE
    )
    
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            headers=self.DEFAULT_HEADERS,
            timeout=self.timeout,
            follow_redirects=True
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def fetch(self, url: str) -> Optional[str]:
        """URL에서 HTML 가져오기"""
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"[ERROR] Failed to fetch {url}: {e}")
            return None
    
    def extract_emails(self, text: str) -> List[str]:
        """텍스트에서 이메일 주소 추출"""
        if not text:
            return []
        
        emails = self.EMAIL_PATTERN.findall(text)
        # 중복 제거 및 유효하지 않은 이메일 필터링
        valid_emails = []
        seen = set()
        
        for email in emails:
            email_lower = email.lower()
            # 이미지 파일 확장자 등 필터링
            if email_lower in seen:
                continue
            if any(ext in email_lower for ext in ['.png', '.jpg', '.gif', '.svg', '.webp']):
                continue
            if email_lower.startswith('example@') or email_lower.endswith('@example.com'):
                continue
                
            seen.add(email_lower)
            valid_emails.append(email)
        
        return valid_emails
    
    @abstractmethod
    async def search(self, keyword: str, pages: int = 5) -> List[Dict[str, Any]]:
        """검색 수행 (하위 클래스에서 구현)"""
        pass
    
    @abstractmethod
    async def get_company_detail(self, company_url: str) -> Dict[str, Any]:
        """회사 상세 정보 가져오기 (하위 클래스에서 구현)"""
        pass
