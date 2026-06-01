import asyncio

from engine.dedup import DedupStore
from engine.pipeline import RunPipeline
from engine.sheets import JobSetting, ScheduleRow
from engine.validator import EmailValidator


class FakeCrawlerService:
    async def crawl(self, sites, keywords, pages):
        return [{
            "company_name": "A",
            "emails": ["recruit@a.com"],
            "job_title": "t",
            "company_url": "u",
            "homepage": "h",
            "source": "saramin",
        }]


class FakeSmartlead:
    def __init__(self):
        self.pushed = []

    def push_leads(self, campaign_id, records):
        from engine.smartlead import PushResult

        self.pushed.append((campaign_id, [record["email"] for record in records]))
        return PushResult(accepted=list(records), failed=[])


class FakeSheet:
    def __init__(self):
        self.history = []
        self.warnings = []
        self.status = []

    def append_history(self, **kwargs):
        self.history.append(kwargs)

    def append_warning(self, run_id, kind, detail, value=""):
        self.warnings.append(kind)

    def set_schedule_keyword(self, row_number, keyword, source):
        pass

    def set_schedule_status(self, row_number, status):
        self.status.append((row_number, status))


class FakeAlert:
    def suspended(self, campaign_id):
        return False


def job():
    return JobSetting(
        industry="물류",
        sites=["saramin"],
        campaign_id="42",
        interval_days=3,
        topup_count=5,
        pages="1-5",
        enabled=True,
    )


def test_pipeline_pushes_and_records(session):
    row = ScheduleRow(2, "2026-06-04", "물류", "3PL", "manual", "예정")
    sheet = FakeSheet()
    smartlead = FakeSmartlead()
    pipeline = RunPipeline(
        session=session,
        crawler=FakeCrawlerService(),
        validator=EmailValidator(session, mx_lookup=lambda domain: True),
        dedup=DedupStore(session),
        smartlead=smartlead,
        sheet=sheet,
        alert=FakeAlert(),
        min_pass_rate=0.4,
    )

    asyncio.run(pipeline.run_row("r1", row, job()))

    assert smartlead.pushed == [("42", ["recruit@a.com"])]
    assert sheet.history[0]["push_status"] == "accepted"
    assert (2, "✅완료") in sheet.status


def test_pipeline_suspended_skips_push(session):
    row = ScheduleRow(2, "2026-06-04", "물류", "3PL", "manual", "예정")
    sheet = FakeSheet()
    smartlead = FakeSmartlead()

    class Suspended:
        def suspended(self, campaign_id):
            return True

    pipeline = RunPipeline(
        session=session,
        crawler=FakeCrawlerService(),
        validator=EmailValidator(session, mx_lookup=lambda domain: True),
        dedup=DedupStore(session),
        smartlead=smartlead,
        sheet=sheet,
        alert=Suspended(),
        min_pass_rate=0.4,
    )

    asyncio.run(pipeline.run_row("r1", row, job()))

    assert smartlead.pushed == []
    assert sheet.history[0]["push_status"] == "suspended"
