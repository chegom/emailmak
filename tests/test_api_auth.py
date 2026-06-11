from fastapi.testclient import TestClient

import server


def test_login_success(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    client = TestClient(server.app)
    resp = client.post("/api/login", json={"password": "secret123"})
    assert resp.status_code == 200
    assert resp.json()["token"]


def test_login_wrong_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    client = TestClient(server.app)
    resp = client.post("/api/login", json={"password": "nope"})
    assert resp.status_code == 401


def test_login_no_protection_returns_empty_token(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    client = TestClient(server.app)
    resp = client.post("/api/login", json={"password": ""})
    assert resp.status_code == 200
    assert resp.json()["token"] == ""
