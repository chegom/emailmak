"""
Email Extractor
회사 홈페이지에서 이메일 주소를 추출하는 모듈
"""
import re
import httpx
from bs4 import BeautifulSoup
from typing import List, Set, Optional
from urllib.parse import urljoin, urlparse


class EmailExtractor:
    """회사 홈페이지에서 이메일 추출"""
    
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    EMAIL_PATTERN = re.compile(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        re.IGNORECASE
    )
    
    # 연락처 관련 키워드 (한국어/영어)
    CONTACT_KEYWORDS = [
        'contact', 'about', 'company', 'footer',
        '문의', '연락', '회사소개', '고객센터', '고객지원'
    ]
    
    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
    
    async def extract_from_url(self, url: str) -> List[str]:
        """URL에서 이메일 추출"""
        if not url:
            return []
        
        # URL 정규화
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        emails: Set[str] = set()
        
        async with httpx.AsyncClient(
            headers=self.DEFAULT_HEADERS,
            timeout=self.timeout,
            follow_redirects=True,
            verify=False  # SSL 인증서 오류 무시
        ) as client:
            # 1. 메인 페이지 크롤링
            main_emails = await self._extract_from_page(client, url)
            emails.update(main_emails)
            
            # 2. 연락처/회사소개 페이지 찾아서 크롤링
            contact_urls = await self._find_contact_pages(client, url)
            for contact_url in contact_urls[:3]:  # 최대 3개 페이지만
                page_emails = await self._extract_from_page(client, contact_url)
                emails.update(page_emails)
        
        return list(emails)
    
    async def _extract_from_page(self, client: httpx.AsyncClient, url: str) -> Set[str]:
        """단일 페이지에서 이메일 추출"""
        try:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
            
            # HTML에서 이메일 추출
            emails = self._extract_emails(html)
            
            # mailto: 링크에서 추출
            soup = BeautifulSoup(html, 'lxml')
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.startswith('mailto:'):
                    email = href.replace('mailto:', '').split('?')[0].strip()
                    if self._is_valid_email(email):
                        emails.add(email)
            
            return emails
            
        except Exception as e:
            print(f"[WARN] Failed to extract from {url}: {e}")
            return set()
    
    async def _find_contact_pages(self, client: httpx.AsyncClient, base_url: str) -> List[str]:
        """연락처/회사소개 페이지 URL 찾기"""
        try:
            response = await client.get(base_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
            contact_urls = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text().lower()
                href_lower = href.lower()
                
                # 키워드 매칭
                if any(kw in text or kw in href_lower for kw in self.CONTACT_KEYWORDS):
                    full_url = urljoin(base_url, href)
                    # 같은 도메인인지 확인
                    if urlparse(full_url).netloc == urlparse(base_url).netloc:
                        if full_url not in contact_urls:
                            contact_urls.append(full_url)
            
            return contact_urls
            
        except Exception:
            return []
    
    def _extract_emails(self, text: str) -> Set[str]:
        """텍스트에서 이메일 추출"""
        if not text:
            return set()
        
        raw_emails = self.EMAIL_PATTERN.findall(text)
        return {email for email in raw_emails if self._is_valid_email(email)}
    
    def _is_valid_email(self, email: str) -> bool:
        """유효한 이메일인지 확인"""
        email_lower = email.lower()
        
        # 이미지/파일 확장자 필터
        invalid_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js']
        if any(ext in email_lower for ext in invalid_extensions):
            return False
        
        # 예시 이메일 필터
        if 'example' in email_lower or 'test@' in email_lower:
            return False
        
        # 너무 짧은 도메인 필터
        parts = email_lower.split('@')
        if len(parts) != 2 or len(parts[1]) < 4:
            return False
        
        return True
