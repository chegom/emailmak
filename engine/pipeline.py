"""Run one due schedule row through crawl, validation, dedup, push, and recording."""
from datetime import datetime


class RunPipeline:
    def __init__(self, session, crawler, validator, dedup, smartlead, sheet, alert, min_pass_rate=0.40):
        self.session = session
        self.crawler = crawler
        self.validator = validator
        self.dedup = dedup
        self.smartlead = smartlead
        self.sheet = sheet
        self.alert = alert
        self.min_pass_rate = min_pass_rate

    async def run_row(self, run_id, row, job):
        keywords = [keyword.strip() for keyword in row.keyword.split(",") if keyword.strip()]
        companies = await self.crawler.crawl(job.sites, keywords, job.pages)
        if not companies:
            self.sheet.append_warning(run_id, "crawl_zero", f"{job.industry}/{','.join(job.sites)}")

        validation = self.validator.validate(companies)
        if validation.pass_rate < self.min_pass_rate and (validation.valid or validation.dropped):
            self.sheet.append_warning(run_id, "low_pass_rate", job.industry, f"{validation.pass_rate * 100:.0f}%")

        fresh = self.dedup.filter_new(validation.valid)

        if self.alert.suspended(job.campaign_id):
            self._record(run_id, row, job, fresh, "suspended", "")
        else:
            push = self.smartlead.push_leads(job.campaign_id, fresh)
            self.dedup.mark_pushed(push.accepted, job.campaign_id)
            accepted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._record(run_id, row, job, push.accepted, "accepted", accepted_at)
            self._record(run_id, row, job, push.failed, "failed", "")

        self.sheet.set_schedule_status(row.row_number, "✅완료")

    def _record(self, run_id, row, job, records, push_status, accepted_at):
        for record in records:
            self.sheet.append_history(
                run_id=run_id,
                company=record.get("company_name"),
                email=record["email"],
                industry=job.industry,
                keyword=row.keyword,
                site=record.get("source"),
                campaign_id=job.campaign_id,
                verdict="role" if record.get("is_role") else "pass",
                is_role=record.get("is_role", False),
                push_status=push_status,
                accepted_at=accepted_at,
                note="",
            )
