from engine.dedup import DedupStore
from engine.models import PushedEmail


def rec(email, **kwargs):
    data = {"email": email, "domain": email.split("@")[1]}
    data.update(kwargs)
    return data


def test_filter_new_excludes_already_pushed(session):
    session.add(PushedEmail(email="old@x.com", domain="x.com", campaign_id="1"))
    session.commit()
    store = DedupStore(session)
    fresh = store.filter_new([rec("old@x.com"), rec("new@x.com")])
    assert [record["email"] for record in fresh] == ["new@x.com"]


def test_filter_new_normalizes_case(session):
    session.add(PushedEmail(email="a@x.com", domain="x.com", campaign_id="1"))
    session.commit()
    store = DedupStore(session)
    fresh = store.filter_new([rec("A@X.com")])
    assert fresh == []


def test_mark_pushed_records_accepted_only(session):
    store = DedupStore(session)
    store.mark_pushed([rec("a@x.com"), rec("b@y.com")], campaign_id="42")
    assert session.get(PushedEmail, "a@x.com").campaign_id == "42"
    assert session.get(PushedEmail, "b@y.com") is not None


def test_mark_pushed_is_idempotent(session):
    store = DedupStore(session)
    store.mark_pushed([rec("a@x.com")], campaign_id="1")
    store.mark_pushed([rec("a@x.com")], campaign_id="1")
    assert session.query(PushedEmail).count() == 1


def test_backfill_inserts_accepted(session):
    store = DedupStore(session)
    store.backfill([rec("a@x.com", campaign_id="9"), rec("b@y.com", campaign_id="9")])
    assert session.query(PushedEmail).count() == 2
