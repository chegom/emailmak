"""Google Sheets control panel adapter."""
import json
from dataclasses import dataclass
from datetime import datetime

TAB_SETTINGS = "⚙️설정"
TAB_SCHEDULE = "📅키워드스케줄"
TAB_HISTORY = "발송내역"
TAB_WARN = "⚠️경고"

SCHEDULE_COLUMNS = {"예정일시": 1, "산업군": 2, "키워드": 3, "출처": 4, "상태": 5}


@dataclass
class JobSetting:
    industry: str
    sites: list
    campaign_id: str
    interval_days: int
    topup_count: int
    pages: str
    enabled: bool


@dataclass
class ScheduleRow:
    row_number: int
    when: str
    industry: str
    keyword: str
    source: str
    status: str


def open_control_sheet(credentials_json: str, sheet_url: str):
    import gspread

    client = gspread.service_account_from_dict(json.loads(credentials_json))
    return client.open_by_url(sheet_url)


class SheetControl:
    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet

    def _worksheet(self, title: str):
        return self.spreadsheet.worksheet(title)

    def read_settings(self) -> list:
        settings = []
        for row in self._worksheet(TAB_SETTINGS).get_all_records():
            if str(row.get("활성화", "")).strip().upper() != "Y":
                continue
            settings.append(JobSetting(
                industry=str(row.get("산업군", "")).strip(),
                sites=[site.strip() for site in str(row.get("사이트", "")).split(",") if site.strip()],
                campaign_id=str(row.get("캠페인ID", "")).strip(),
                interval_days=int(row.get("주기(일)") or 3),
                topup_count=int(row.get("미리채울회수") or 5),
                pages=str(row.get("페이지", "") or "1-5").strip(),
                enabled=True,
            ))
        return settings

    def read_schedule(self) -> list:
        rows = []
        for index, row in enumerate(self._worksheet(TAB_SCHEDULE).get_all_records(), start=2):
            rows.append(ScheduleRow(
                row_number=index,
                when=str(row.get("예정일시", "")).strip(),
                industry=str(row.get("산업군", "")).strip(),
                keyword=str(row.get("키워드", "")).strip(),
                source=str(row.get("출처", "")).strip(),
                status=str(row.get("상태", "")).strip(),
            ))
        return rows

    def append_schedule(self, when: str, industry: str, keyword: str, source: str, status: str = "예정"):
        self._worksheet(TAB_SCHEDULE).append_row([when, industry, keyword, source, status])

    def set_schedule_status(self, row_number: int, status: str):
        self._worksheet(TAB_SCHEDULE).update_cell(row_number, SCHEDULE_COLUMNS["상태"], status)

    def set_schedule_keyword(self, row_number: int, keyword: str, source: str):
        worksheet = self._worksheet(TAB_SCHEDULE)
        worksheet.update_cell(row_number, SCHEDULE_COLUMNS["키워드"], keyword)
        worksheet.update_cell(row_number, SCHEDULE_COLUMNS["출처"], source)

    def append_history(
        self,
        run_id,
        company,
        email,
        industry,
        keyword,
        site,
        campaign_id,
        verdict,
        is_role,
        push_status,
        accepted_at,
        note,
    ):
        self._worksheet(TAB_HISTORY).append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            run_id,
            company,
            email,
            industry,
            keyword,
            site,
            campaign_id,
            verdict,
            "Y" if is_role else "",
            push_status,
            accepted_at or "",
            note or "",
        ])

    def append_warning(self, run_id, kind, detail, value=""):
        self._worksheet(TAB_WARN).append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            run_id,
            kind,
            detail,
            str(value),
        ])
