from datetime import datetime

from engine.models import MxCache
from engine.validator import EmailValidator


def make_validator(session, mx_ok=True):
    return EmailValidator(session, mx_lookup=lambda domain: mx_ok)


def company(name, emails):
    return {
        "company_name": name,
        "emails": emails,
        "job_title": "t",
        "source": "wanted",
        "homepage": "h",
        "company_url": "c",
    }


def test_syntax_invalid_dropped(session):
    validator = make_validator(session)
    result = validator.validate([company("A", ["not-an-email", "good@valid.com"])])
    emails = {record["email"] for record in result.valid}
    assert emails == {"good@valid.com"}
    assert any(drop["reason"] == "syntax" for drop in result.dropped)


def test_system_address_dropped(session):
    validator = make_validator(session)
    result = validator.validate([company("A", ["no-reply@valid.com", "postmaster@valid.com"])])
    assert result.valid == []
    assert all(drop["reason"] == "system" for drop in result.dropped)


def test_disposable_domain_dropped(session):
    validator = make_validator(session)
    result = validator.validate([company("A", ["x@mailinator.com"])])
    assert result.valid == []
    assert result.dropped[0]["reason"] == "disposable"


def test_role_address_kept_and_flagged(session):
    validator = make_validator(session)
    result = validator.validate([company("A", ["recruit@valid.com", "ceo@valid.com"])])
    by_email = {record["email"]: record for record in result.valid}
    assert by_email["recruit@valid.com"]["is_role"] is True
    assert by_email["ceo@valid.com"]["is_role"] is False


def test_mx_missing_dropped(session):
    validator = make_validator(session, mx_ok=False)
    result = validator.validate([company("A", ["x@nomx.com"])])
    assert result.valid == []
    assert result.dropped[0]["reason"] == "no_mx"


def test_mx_cache_hit_skips_lookup(session):
    calls = []
    validator = EmailValidator(session, mx_lookup=lambda domain: calls.append(domain) or True)
    session.add(MxCache(domain="cached.com", mx_valid=True, checked_at=datetime.utcnow()))
    session.commit()
    validator.validate([company("A", ["x@cached.com"])])
    assert calls == []


def test_pass_rate(session):
    validator = make_validator(session)
    result = validator.validate([company("A", ["good@valid.com", "bad"])])
    assert result.pass_rate == 0.5
