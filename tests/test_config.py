import os
import pytest


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret-key-please-rotate")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id-123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret-abc")
    monkeypatch.setenv("ALLOWED_OAUTH_DOMAIN", "example.com,test.com")
    monkeypatch.setenv("ALLOWED_OAUTH_EMAILS", "alice@external.com")

    from importlib import reload
    from app import config as config_module
    reload(config_module)

    s = config_module.get_settings()
    assert s.app_secret_key == "test-secret-key-please-rotate"
    assert s.database_url.endswith("test.db")
    assert s.google_oauth_client_id == "client-id-123"
    assert s.allowed_oauth_domains == ["example.com", "test.com"]
    assert s.allowed_oauth_emails_list == ["alice@external.com"]


def test_settings_defaults_when_optional_unset(monkeypatch):
    for k in ["ALLOWED_OAUTH_DOMAIN", "ALLOWED_OAUTH_EMAILS"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "cs")

    from importlib import reload
    from app import config as config_module
    reload(config_module)

    s = config_module.get_settings()
    assert s.allowed_oauth_domains == []
    assert s.allowed_oauth_emails_list == []


def test_settings_missing_required_raises(monkeypatch):
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)

    from importlib import reload
    from app import config as config_module
    reload(config_module)

    with pytest.raises(Exception):
        config_module.get_settings()
