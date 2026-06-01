"""Schedule top-up planning for future keyword rows."""
from datetime import date, datetime, timedelta


def _parse_date(value: str) -> date:
    date_text = (value or "").strip().split(" ")[0]
    return datetime.strptime(date_text, "%Y-%m-%d").date()


class SchedulePlanner:
    def __init__(self, sheet, resolver, today: date = None):
        self.sheet = sheet
        self.resolver = resolver
        self.today = today or date.today()

    def topup(self, settings: list):
        all_rows = self.sheet.read_schedule()

        for job in settings:
            rows = [row for row in all_rows if row.industry == job.industry]
            pending = [row for row in rows if row.status == "예정"]
            need = job.topup_count - len(pending)
            if need <= 0:
                continue

            avoid = [row.keyword for row in rows if row.keyword]
            future_dates = [_parse_date(row.when) for row in pending] or [self.today]
            last_date = max(future_dates)

            for _ in range(need):
                last_date = last_date + timedelta(days=job.interval_days)
                keywords, source = self.resolver.resolve(
                    industry=job.industry,
                    manual="",
                    avoid=avoid,
                    n=5,
                )
                keyword_text = ", ".join(keywords)
                self.sheet.append_schedule(
                    when=last_date.strftime("%Y-%m-%d"),
                    industry=job.industry,
                    keyword=keyword_text,
                    source=source,
                    status="예정",
                )
                avoid.extend(keywords)
