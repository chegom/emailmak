"""
Google Sheets Integration Utilities
"""
import os
import json
import gspread
from typing import List, Dict, Any, Optional

class GoogleSheetExporter:
    def __init__(self):
        self.credentials_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        self.client = None
        
    def authenticate(self):
        """환경변수에서 인증 정보를 로드하여 gspread 클라이언트 인증"""
        if not self.credentials_json:
            raise ValueError("GOOGLE_CREDENTIALS_JSON environment variable is not set")
            
        try:
            creds_dict = json.loads(self.credentials_json)
            self.client = gspread.service_account_from_dict(creds_dict)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON in GOOGLE_CREDENTIALS_JSON")
        except Exception as e:
            raise Exception(f"Failed to authenticate with Google Sheets: {e}")

    def get_service_email(self) -> Optional[str]:
        """서비스 계정 이메일 반환"""
        if not self.credentials_json:
            return None
            
        try:
            creds_dict = json.loads(self.credentials_json)
            return creds_dict.get("client_email")
        except:
            return None

    def export_to_sheet(self, sheet_url: str, data: List[Dict[str, Any]], keyword: str, source: str):
        """
        데이터를 구글 시트에 내보내기 (새 시트 추가 모드)
        
        Args:
            sheet_url: 구글 시트 전체 URL
            data: 회사 정보 리스트
            keyword: 검색어
            source: 검색 출처 (예: 사람인, 잡코리아)
        """
        from datetime import datetime
        
        if not self.client:
            self.authenticate()
            
        try:
            # 시트 열기
            doc = self.client.open_by_url(sheet_url)
            
            # 1. 시트 이름 생성 (예: 물류_사람인_20250126)
            date_str = datetime.now().strftime("%Y%m%d")
            base_title = f"{keyword}_{source}_{date_str}"
            sheet_title = base_title
            
            # 2. 중복 이름 처리 (이미 있으면 (1), (2) 붙임)
            counter = 1
            existing_titles = [ws.title for ws in doc.worksheets()]
            
            while sheet_title in existing_titles:
                sheet_title = f"{base_title} ({counter})"
                counter += 1
                
            # 3. 새 워크시트 생성
            worksheet = doc.add_worksheet(title=sheet_title, rows=max(100, len(data) + 20), cols=20)
                
            # 헤더 준비
            headers = ["회사명", "채용공고 제목", "대표 이메일", "추가 이메일", "홈페이지", "채용사이트 링크", "기업정보 링크", "수집 출처"]
            
            # 데이터 변환
            rows = []
            for company in data:
                emails = company.get('emails', [])
                primary_email = emails[0] if emails else ""
                other_emails = ", ".join(emails[1:]) if len(emails) > 1 else ""
                
                rows.append([
                    company.get('company_name', ''),
                    company.get('job_title', ''),
                    primary_email,
                    other_emails,
                    company.get('homepage', ''),
                    company.get('job_url', ''),
                    company.get('company_url', ''),
                    company.get('source', '')
                ])
                
            # 데이터 쓰기
            worksheet.update(range_name='A1', values=[headers] + rows)
            
            # 헤더 스타일링
            worksheet.format("A1:H1", {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
            })
            
            return True, f"'{sheet_title}' 시트가 추가되었습니다. ({len(rows)}개 회사)"
            
        except Exception as e:
            return False, str(e)
