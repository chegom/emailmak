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

    def export_to_sheet(self, sheet_url: str, data: List[Dict[str, Any]], sheet_name: str = "시트1"):
        """
        데이터를 구글 시트에 내보내기
        
        Args:
            sheet_url: 구글 시트 전체 URL
            data: 회사 정보 리스트
            sheet_name: 데이터를 쓸 시트(탭) 이름 (기본값: '시트1')
        """
        if not self.client:
            self.authenticate()
            
        try:
            # 시트 열기
            doc = self.client.open_by_url(sheet_url)
            
            # 워크시트 선택 또는 생성
            try:
                worksheet = doc.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                # 시트가 없으면 생성 (행 1000개, 열 20개)
                worksheet = doc.add_worksheet(title=sheet_name, rows=1000, cols=20)
                
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
                
            # 기존 데이터 지우고 새로 쓰기 (또는 append 모드로 변경 가능)
            # 여기서는 헤더 + 데이터를 덮어쓰는 방식으로 구현
            worksheet.clear()
            worksheet.update(range_name='A1', values=[headers] + rows)
            
            # 헤더 스타일링 (선택사항)
            worksheet.format("A1:H1", {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
            })
            
            return True, f"{len(rows)}개 회사가 '{doc.title} / {sheet_name}' 에 성공적으로 저장되었습니다."
            
        except Exception as e:
            return False, str(e)
