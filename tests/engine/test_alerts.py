import json

from engine.alerts import AlertMonitor
from engine.models import EngineState


class FakeStats:
    def __init__(self, stats):
        self._stats = stats

    def get_campaign_stats(self, campaign_id):
        return self._stats[campaign_id]


class FakeSheet:
    def __init__(self):
        self.warnings = []

    def append_warning(self, run_id, kind, detail, value=""):
        self.warnings.append((kind, detail, value))


def monitor(session, stats_map, warn=0.05, critical=0.08, sample=50):
    return AlertMonitor(
        session,
        FakeStats(stats_map),
        FakeSheet(),
        warn=warn,
        critical=critical,
        min_sample=sample,
    )


def test_no_alert_below_sample(session):
    alert = monitor(session, {"42": {"sent": 10, "bounced": 9}}, sample=50)
    alert.poll_bounce("r1", ["42"])
    assert alert.sheet.warnings == []
    assert not alert.suspended("42")


def test_warn_on_delta_rate(session):
    alert = monitor(session, {"42": {"sent": 100, "bounced": 6}}, sample=50)
    alert.poll_bounce("r1", ["42"])
    assert alert.sheet.warnings[0][0] == "bounce_warn"
    assert not alert.suspended("42")


def test_critical_suspends(session):
    alert = monitor(session, {"42": {"sent": 100, "bounced": 9}}, sample=50)
    alert.poll_bounce("r1", ["42"])
    assert alert.sheet.warnings[0][0] == "bounce_critical"
    assert alert.suspended("42")


def test_delta_uses_snapshot(session):
    session.add(EngineState(key="bounce_snapshot:42", value=json.dumps({"sent": 90, "bounced": 0})))
    session.commit()
    alert = monitor(session, {"42": {"sent": 100, "bounced": 9}}, sample=50)
    alert.poll_bounce("r1", ["42"])
    assert alert.sheet.warnings == []
