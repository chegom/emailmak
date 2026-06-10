"""
Email Extractor
회사 홈페이지에서 이메일 주소를 추출하는 모듈
"""
import re
import httpx
from bs4 import BeautifulSoup
from typing import Dict, List, Set, Optional
from urllib.parse import urljoin, urlparse

try:
    import dns.asyncresolver
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    # dnspython 미설치 시 MX 검증은 건너뛰고 나머지 기능은 정상 동작
    DNS_AVAILABLE = False


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

    # 콜드메일 발송 시 제거해야 하는 주소 (스팸트랩 / 수신불가 / 비마케팅)
    # 발송하면 반송·스팸신고로 발신 도메인 평판이 떨어진다.
    BLOCKED_LOCAL_PARTS = {
        'noreply', 'no-reply', 'donotreply', 'do-not-reply',
        'postmaster', 'abuse', 'mailer-daemon', 'webmaster',
        'hostmaster', 'spam', 'bounce',
    }

    # 일반(역할 기반) 주소 — 발송은 가능하나 개인 주소보다 응답률이 낮다.
    GENERIC_LOCAL_PARTS = {
        'info', 'contact', 'help', 'support', 'admin', 'office',
        'mail', 'sales', 'cs', 'help-desk', 'helpdesk', 'master',
        'hr', 'recruit', 'job', 'jobs', 'marketing', 'pr', 'press',
        'privacy', 'security', 'legal', 'sns', 'official', 'partnership',
    }

    # 차단 도메인 — 사이트 푸터에 박혀 있는 솔루션사/호스팅/빌더 주소.
    # 대상 회사가 아니라 제작 솔루션 업체의 주소라 발송하면 차단·스팸신고로 이어진다.
    # (SmartLead 실측: Blocked 22% 의 주요 원인)
    BLOCKED_DOMAINS = {
        # 모니터링/플랫폼 잔여물
        'sentry.io', 'wixpress.com', 'sentry-next.wixpress.com',
        'w3.org', 'schema.org',
        # 플레이스홀더
        'example.com', 'example.org', 'example.net', 'test.com',
        'email.com', 'domain.com', 'yourdomain.com', 'company.com',
        'mysite.com', 'website.com', 'sample.com',
        # 글로벌 빌더/호스팅
        'wix.com', 'wordpress.com', 'squarespace.com', 'webflow.com',
        'shopify.com', 'godaddy.com',
        # 국내 호스팅/빌더/쇼핑몰 솔루션
        'cafe24.com', 'cafe24corp.com', 'imweb.me', 'modoo.at',
        'godo.co.kr', 'makeshop.co.kr', 'gabia.com', 'whois.co.kr',
        'hosting.kr', 'dothome.co.kr', 'mireene.com', 'nhn-commerce.com',
        'sixshop.com', 'creatorlink.net',
    }

    # 무료 메일 도메인 — 국내 SMB는 대표 연락처로 자주 사용. 차단하지 않고 라벨로 구분만.
    FREE_MAIL_DOMAINS = {
        'gmail.com', 'naver.com', 'hanmail.net', 'daum.net', 'kakao.com',
        'nate.com', 'outlook.com', 'hotmail.com', 'yahoo.com', 'icloud.com',
    }

    # sentry DSN 키 등 해시형 로컬파트 (예: a1b2c3...32자리hex@...)
    HEX_LOCAL_PATTERN = re.compile(r'^[0-9a-f]{20,}$')

    # 점수 → 발송명단 표시용 라벨
    SCORE_LABELS = {
        0: '개인(회사도메인)',
        1: '일반(회사도메인)',
        2: '개인(타도메인)',
        3: '일반(타도메인)',
    }
    SCORE_LABELS_NO_DOMAIN = {2: '개인', 3: '일반'}

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        # MX 조회 결과 캐시 (도메인 → 메일서버 존재 여부)
        self._mx_cache: Dict[str, bool] = {}
        # 크롤링 세션 내 수집된 이메일 (중복 발송 방지 + 제3자 주소 감지)
        self._seen_emails: Set[str] = set()

    @staticmethod
    def _registrable_domain(host: str) -> str:
        """www. 제거 후 등록 도메인 추정 (예: www.acme.co.kr → acme.co.kr)"""
        host = (host or '').lower().strip()
        if host.startswith('www.'):
            host = host[4:]
        return host

    def _company_domain(self, homepage_url: str) -> str:
        """홈페이지 URL에서 회사 도메인 추출"""
        if not homepage_url:
            return ''
        parsed = homepage_url if homepage_url.startswith(('http://', 'https://')) else 'https://' + homepage_url
        return self._registrable_domain(urlparse(parsed).netloc)

    def _score_email(self, email: str, company_domain: str) -> Optional[int]:
        """
        콜드메일 적합성 점수 (낮을수록 우선, None이면 발송 불가 주소).
        콜드메일은 '대상 회사 도달'이 핵심이므로 도메인 일치를 개인/일반 구분보다 우선:
          0: 회사 도메인 일치 + 개인 주소
          1: 회사 도메인 일치 + 일반(역할) 주소
          2: 도메인 불일치/미상 + 개인 주소 (제3자일 수 있음)
          3: 도메인 불일치/미상 + 일반(역할) 주소
        """
        local, _, domain = email.lower().strip().partition('@')

        # 스팸트랩/수신불가 주소 제외
        if local in self.BLOCKED_LOCAL_PARTS:
            return None

        email_domain = self._registrable_domain(domain)
        domain_match = bool(company_domain) and (
            email_domain == company_domain or email_domain.endswith('.' + company_domain)
        )
        is_generic = local in self.GENERIC_LOCAL_PARTS

        if domain_match and not is_generic:
            return 0
        elif domain_match:
            return 1
        elif not is_generic:
            return 2
        return 3

    def _classify_and_sort(self, emails: Set[str], homepage_url: str) -> List[str]:
        """
        수집된 이메일을 콜드메일 적합성 기준으로 필터링·정렬한다.
        - BLOCKED 주소(스팸트랩/수신불가) 제거
        - 최적 주소가 가장 앞으로 정렬 → emails[0]이 '대표 이메일'이 됨
        """
        company_domain = self._company_domain(homepage_url)

        scored: List[tuple] = []
        for email in emails:
            email = email.lower().strip()
            score = self._score_email(email, company_domain)
            if score is not None:
                scored.append((score, email))

        scored.sort(key=lambda x: (x[0], x[1]))
        return [email for _, email in scored]

    def label_emails(self, emails: List[str], homepage_url: str) -> List[str]:
        """
        이메일 목록을 발송명단 표시용 유형 라벨로 변환 (emails와 같은 순서).
        예: ['개인(회사도메인)', '일반(회사도메인)', '개인(타도메인)']
        """
        company_domain = self._company_domain(homepage_url)
        labels = []
        for email in emails:
            score = self._score_email(email, company_domain)
            email_domain = self._registrable_domain(email.rpartition('@')[2])
            if score is None:
                labels.append('발송불가')
            elif email_domain in self.FREE_MAIL_DOMAINS:
                # 국내 SMB 대표 연락처로 흔함 — 타도메인과 구분해 표시
                labels.append('개인(무료메일)' if score == 2 else '일반(무료메일)')
            elif not company_domain:
                labels.append(self.SCORE_LABELS_NO_DOMAIN.get(score, self.SCORE_LABELS[score]))
            else:
                labels.append(self.SCORE_LABELS[score])
        return labels

    async def _has_mail_server(self, domain: str) -> bool:
        """
        도메인에 실제 메일 서버(MX, 없으면 A 레코드)가 있는지 확인.
        - 조회 실패(타임아웃 등) 시에는 True 반환 → 인프라 문제로 멀쩡한 주소를 버리지 않음
        - 도메인이 아예 없거나(MX/A 모두 없음) NXDOMAIN이면 False → 반송 확정 주소 제거
        """
        if not DNS_AVAILABLE:
            return True

        domain = domain.lower().strip()
        if domain in self._mx_cache:
            return self._mx_cache[domain]

        result = True
        try:
            resolver = dns.asyncresolver.Resolver()
            resolver.lifetime = 3.0
            try:
                await resolver.resolve(domain, 'MX')
                result = True
            except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
                # MX가 없으면 A 레코드로 폴백 (RFC 5321)
                try:
                    await resolver.resolve(domain, 'A')
                    result = True
                except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
                    result = False
            except dns.resolver.NXDOMAIN:
                result = False
        except Exception:
            # 타임아웃 등 일시 오류 → 보수적으로 유지
            result = True

        self._mx_cache[domain] = result
        return result

    async def _verify_mail_servers(self, emails: List[str]) -> List[str]:
        """반송이 확정된(메일서버 없는) 도메인의 이메일 제거"""
        verified = []
        for email in emails:
            domain = email.rpartition('@')[2]
            if await self._has_mail_server(domain):
                verified.append(email)
        return verified
    
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

        # 3. 콜드메일 적합성 기준으로 필터링·정렬 (스팸트랩 제거, 대표 이메일 우선)
        sorted_emails = self._classify_and_sort(emails, url)

        # 4. MX 레코드 검증 — 메일서버 없는 도메인(반송 확정) 제거
        verified = await self._verify_mail_servers(sorted_emails)

        # 5. 세션 내 중복 제거 — 같은 이메일이 여러 회사에서 나오면
        #    제작사/솔루션사 공용 주소일 가능성이 높고, 중복 발송은 스팸신고로 직결
        deduped = []
        for email in verified:
            if email not in self._seen_emails:
                self._seen_emails.add(email)
                deduped.append(email)
        return deduped
    
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

        local, domain = parts

        # 해시형 로컬파트 (sentry DSN 키 등 크롤링 잔여물) / 비정상 길이
        if self.HEX_LOCAL_PATTERN.match(local) or len(local) > 40:
            return False

        # 솔루션사/호스팅/빌더 도메인 — 대상 회사 주소가 아님
        email_domain = self._registrable_domain(domain)
        if email_domain in self.BLOCKED_DOMAINS or any(
            email_domain.endswith('.' + blocked) for blocked in self.BLOCKED_DOMAINS
        ):
            return False

        return True
