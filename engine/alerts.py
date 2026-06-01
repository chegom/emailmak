"""Bounce alerts based on stat deltas and minimum sample size."""
import json

from engine.models import EngineState

SUSPEND_PREFIX = "suspended:"
SNAPSHOT_PREFIX = "bounce_snapshot:"


class AlertMonitor:
    def __init__(self, session, smartlead, sheet, warn=0.05, critical=0.08, min_sample=50):
        self.session = session
        self.smartlead = smartlead
        self.sheet = sheet
        self.warn = warn
        self.critical = critical
        self.min_sample = min_sample

    def _get(self, key: str):
        row = self.session.get(EngineState, key)
        return row.value if row else None

    def _set(self, key: str, value: str):
        row = self.session.get(EngineState, key)
        if row:
            row.value = value
        else:
            self.session.add(EngineState(key=key, value=value))
        self.session.commit()

    def suspended(self, campaign_id: str) -> bool:
        return self._get(SUSPEND_PREFIX + campaign_id) == "1"

    def _suspend(self, campaign_id: str):
        self._set(SUSPEND_PREFIX + campaign_id, "1")

    def poll_bounce(self, run_id: str, campaign_ids: list):
        for campaign_id in campaign_ids:
            stats = self.smartlead.get_campaign_stats(campaign_id)
            snapshot_raw = self._get(SNAPSHOT_PREFIX + campaign_id)
            snapshot = json.loads(snapshot_raw) if snapshot_raw else {"sent": 0, "bounced": 0}

            delta_sent = stats["sent"] - snapshot["sent"]
            delta_bounced = stats["bounced"] - snapshot["bounced"]
            if delta_sent >= self.min_sample:
                rate = delta_bounced / delta_sent if delta_sent else 0.0
                pct = f"{rate * 100:.1f}%"
                if rate >= self.critical:
                    self.sheet.append_warning(run_id, "bounce_critical", campaign_id, pct)
                    self._suspend(campaign_id)
                elif rate >= self.warn:
                    self.sheet.append_warning(run_id, "bounce_warn", campaign_id, pct)

            self._set(
                SNAPSHOT_PREFIX + campaign_id,
                json.dumps({"sent": stats["sent"], "bounced": stats["bounced"]}),
            )
