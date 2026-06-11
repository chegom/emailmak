"""Regression: engine_state schema must be created at startup regardless of
ENGINE_ENABLED, otherwise /api/settings and /api/export/sheet 500 with
'no such table: engine_state'."""
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

import server


def test_ensure_state_schema_creates_engine_state_table(monkeypatch):
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(server, "engine_state_engine", eng)

    # Table absent before
    assert "engine_state" not in inspect(eng).get_table_names()

    server.ensure_state_schema()

    # Table present after
    assert "engine_state" in inspect(eng).get_table_names()
