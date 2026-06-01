from engine.sheets import SheetControl


class FakeWorksheet:
    def __init__(self, rows):
        self._records = rows
        self.appended = []
        self.updated = []

    def get_all_records(self):
        return list(self._records)

    def append_row(self, values, value_input_option="RAW"):
        self.appended.append(values)

    def update_cell(self, row, col, value):
        self.updated.append((row, col, value))


class FakeSpreadsheet:
    def __init__(self, tabs):
        self._tabs = tabs

    def worksheet(self, title):
        return self._tabs[title]


def test_read_settings_only_active():
    worksheet = FakeWorksheet([
        {
            "산업군": "물류",
            "사이트": "saramin",
            "캠페인ID": "42",
            "주기(일)": 3,
            "미리채울회수": 5,
            "페이지": "1-5",
            "활성화": "Y",
        },
        {
            "산업군": "헬스",
            "사이트": "wanted",
            "캠페인ID": "9",
            "주기(일)": 3,
            "미리채울회수": 5,
            "페이지": "",
            "활성화": "N",
        },
    ])
    sheet = SheetControl(FakeSpreadsheet({"⚙️설정": worksheet}))
    settings = sheet.read_settings()
    assert len(settings) == 1
    assert settings[0].industry == "물류"
    assert settings[0].campaign_id == "42"
    assert settings[0].interval_days == 3


def test_read_schedule_returns_row_numbers():
    worksheet = FakeWorksheet([
        {"예정일시": "2026-06-04", "산업군": "물류", "키워드": "3PL", "출처": "ai", "상태": "예정"},
    ])
    sheet = SheetControl(FakeSpreadsheet({"📅키워드스케줄": worksheet}))
    rows = sheet.read_schedule()
    assert rows[0].row_number == 2
    assert rows[0].keyword == "3PL"


def test_append_warning():
    worksheet = FakeWorksheet([])
    sheet = SheetControl(FakeSpreadsheet({"⚠️경고": worksheet}))
    sheet.append_warning(run_id="r1", kind="bounce_warn", detail="물류/42", value="6%")
    assert worksheet.appended[0][1:] == ["r1", "bounce_warn", "물류/42", "6%"]


def test_update_row_status():
    worksheet = FakeWorksheet([
        {"예정일시": "x", "산업군": "물류", "키워드": "", "출처": "ai", "상태": "예정"},
    ])
    sheet = SheetControl(FakeSpreadsheet({"📅키워드스케줄": worksheet}))
    sheet.set_schedule_status(row_number=2, status="✅완료")
    assert (2, 5, "✅완료") in worksheet.updated
