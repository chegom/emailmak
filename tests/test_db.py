from app.db import engine, get_session, Base
from sqlalchemy import text


def test_engine_uses_settings_url():
    assert "sqlite" in str(engine.url)


def test_get_session_yields_usable_session():
    gen = get_session()
    session = next(gen)
    try:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_base_metadata_available():
    assert hasattr(Base, "metadata")
