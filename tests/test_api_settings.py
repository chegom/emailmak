import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import server
from engine.db import Base
import engine.models  # noqa: F401


@pytest.fixture
def client_and_session(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)  # 보호 비활성으로 단순화
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
    opened = []

    def get_service_email(self):
        return "bot@project.iam.gserviceaccount.com"

    def authenticate(self):
        pass

    @property
    def client(self):
        return self

    def open_by_url(self, url):
        if "fail" in url:
            raise Exception("no access")
        _FakeExporter.opened.append(url)
        return object()


def test_get_settings_empty(client_and_session):
    client, _, _ = client_and_session
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["sheet_url"] is None


def test_post_then_get_settings(client_and_session):
    client, _, monkeypatch = client_and_session
    monkeypatch.setattr(server, "GoogleSheetExporter", _FakeExporter)
    url = "https://docs.google.com/spreadsheets/d/abc123"
    resp = client.post("/api/settings", json={"sheet_url": url})
    assert resp.status_code == 200
    assert client.get("/api/settings").json()["sheet_url"] == url


def test_post_invalid_url(client_and_session):
    client, _, monkeypatch = client_and_session
    monkeypatch.setattr(server, "GoogleSheetExporter", _FakeExporter)
    resp = client.post("/api/settings", json={"sheet_url": "https://example.com/x"})
    assert resp.status_code == 400


def test_post_unopenable_sheet(client_and_session):
    client, _, monkeypatch = client_and_session
    monkeypatch.setattr(server, "GoogleSheetExporter", _FakeExporter)
    url = "https://docs.google.com/spreadsheets/d/fail"
    resp = client.post("/api/settings", json={"sheet_url": url})
    assert resp.status_code == 400
