from datetime import date

from engine.planner import SchedulePlanner
from engine.sheets import JobSetting, ScheduleRow


class FakeSheet:
    def __init__(self, rows):
        self._rows = rows
        self.appended = []

    def read_schedule(self):
        return list(self._rows)

    def append_schedule(self, when, industry, keyword, source, status="예정"):
        self.appended.append((when, industry, keyword, source, status))


class FakeResolver:
    def resolve(self, industry, manual, avoid, n):
        return [f"kw-{len(avoid)}"], "ai"


def job(industry, n=3, interval=3):
    return JobSetting(
        industry=industry,
        sites=["saramin"],
        campaign_id="1",
        interval_days=interval,
        topup_count=n,
        pages="1-5",
        enabled=True,
    )


def test_topup_fills_to_n():
    sheet = FakeSheet([
        ScheduleRow(2, "2026-06-04", "물류", "3PL", "manual", "예정"),
    ])
    planner = SchedulePlanner(sheet, FakeResolver(), today=date(2026, 6, 1))
    planner.topup([job("물류", n=3)])
    assert len(sheet.appended) == 2
    assert [row[0] for row in sheet.appended] == ["2026-06-07", "2026-06-10"]


def test_topup_skips_when_full():
    sheet = FakeSheet([
        ScheduleRow(2, "2026-06-04", "물류", "3PL", "ai", "예정"),
        ScheduleRow(3, "2026-06-07", "물류", "WMS", "ai", "예정"),
        ScheduleRow(4, "2026-06-10", "물류", "콜드체인", "ai", "예정"),
    ])
    planner = SchedulePlanner(sheet, FakeResolver(), today=date(2026, 6, 1))
    planner.topup([job("물류", n=3)])
    assert sheet.appended == []


def test_topup_avoid_uses_completed_and_pending():
    sheet = FakeSheet([
        ScheduleRow(2, "2026-06-01", "물류", "3PL", "ai", "✅완료"),
        ScheduleRow(3, "2026-06-04", "물류", "WMS", "ai", "예정"),
    ])
    captured = {}

    class CapturingResolver:
        def resolve(self, industry, manual, avoid, n):
            captured["avoid"] = list(avoid)
            return ["새키워드"], "ai"

    planner = SchedulePlanner(sheet, CapturingResolver(), today=date(2026, 6, 1))
    planner.topup([job("물류", n=2)])
    assert "3PL" in captured["avoid"]
    assert "WMS" in captured["avoid"]
