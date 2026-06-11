import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import server
from engine.db import Base
import engine.models  # noqa: F401
from engine.kv import set_setting


@pytest.fixture
def client_and_session(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng, expire_on_commit=False)
    s = Session()
    def _override():
        yield s

    server.app.dependency_overrides[server.get_session] = _override
    client = TestClient(server.app)
    try:
        yield client, s, monkeypatch
    finally:
        server.app.dependency_overrides.clear()
        s.close()
        eng.dispose()


class _FakeExporter:
    used_url = None

    def export_to_sheet(self, sheet_url, data, keyword, source):
        _FakeExporter.used_url = sheet_url
        return True, f"saved {len(data)} rows"


def test_export_without_configured_sheet_400(client_and_session):
    client, _, _ = client_and_session
    resp = client.post("/api/export/sheet", json={"companies": [], "keyword": "k", "source": "사람인"})
    assert resp.status_code == 400


def test_export_uses_server_stored_url(client_and_session):
    client, s, monkeypatch = client_and_session
    set_setting(s, "crawl_sheet_url", "https://docs.google.com/spreadsheets/d/stored")
    s.commit()
    monkeypatch.setattr(server, "GoogleSheetExporter", _FakeExporter)
    resp = client.post(
        "/api/export/sheet",
        json={"companies": [{"company_name": "A"}], "keyword": "k", "source": "사람인",
              "sheet_url": "https://docs.google.com/spreadsheets/d/IGNORED"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert _FakeExporter.used_url == "https://docs.google.com/spreadsheets/d/stored"
