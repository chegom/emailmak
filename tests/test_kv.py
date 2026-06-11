import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from engine.db import Base
import engine.models  # noqa: F401
from engine.kv import get_setting, set_setting


@pytest.fixture
def session():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


def test_get_missing_returns_none(session):
    assert get_setting(session, "crawl_sheet_url") is None


def test_set_then_get(session):
    set_setting(session, "crawl_sheet_url", "https://docs.google.com/spreadsheets/d/abc")
    session.commit()
    assert get_setting(session, "crawl_sheet_url") == "https://docs.google.com/spreadsheets/d/abc"


def test_set_overwrites(session):
    set_setting(session, "crawl_sheet_url", "old")
    session.commit()
    set_setting(session, "crawl_sheet_url", "new")
    session.commit()
    assert get_setting(session, "crawl_sheet_url") == "new"
