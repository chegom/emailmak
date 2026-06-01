from engine.models import EngineState, MxCache, PushedEmail, RunLock


def test_engine_state_roundtrip(session):
    session.add(EngineState(key="suspended:123", value="1"))
    session.commit()
    row = session.get(EngineState, "suspended:123")
    assert row.value == "1"


def test_pushed_email_unique(session):
    session.add(PushedEmail(email="a@x.com", domain="x.com", campaign_id="123"))
    session.commit()
    assert session.get(PushedEmail, "a@x.com").domain == "x.com"


def test_mx_cache_roundtrip(session):
    session.add(MxCache(domain="x.com", mx_valid=True))
    session.commit()
    assert session.get(MxCache, "x.com").mx_valid is True


def test_run_lock_roundtrip(session):
    session.add(RunLock(row_key="물류|2026-06-04 09:00"))
    session.commit()
    assert session.get(RunLock, "물류|2026-06-04 09:00") is not None
