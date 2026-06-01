import importlib

import pytest


def _fresh_settings(monkeypatch, **env):
    # OAuth env is intentionally absent; the engine must not depend on it.
    for key in ("APP_SECRET_KEY", "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import engine.settings as settings_module

    importlib.reload(settings_module)
    settings_module.get_engine_settings.cache_clear()
    return settings_module.get_engine_settings()


def test_loads_without_oauth_env(monkeypatch):
    cfg = _fresh_settings(
        monkeypatch,
        SMARTLEAD_API_KEY="sl-key",
        GEMINI_API_KEY="gm-key",
        CONTROL_SHEET_URL="https://docs.google.com/x",
        GOOGLE_CREDENTIALS_JSON="{}",
    )
    assert cfg.smartlead_api_key == "sl-key"
    assert cfg.gemini_api_key == "gm-key"
    assert cfg.control_sheet_url.endswith("/x")


def test_threshold_defaults(monkeypatch):
    cfg = _fresh_settings(
        monkeypatch,
        SMARTLEAD_API_KEY="x",
        GEMINI_API_KEY="x",
        CONTROL_SHEET_URL="x",
        GOOGLE_CREDENTIALS_JSON="{}",
    )
    assert cfg.bounce_warn == 0.05
    assert cfg.bounce_critical == 0.08
    assert cfg.min_bounce_sample == 50
    assert cfg.min_pass_rate == 0.40
    assert cfg.smartlead_daily_limit == 200
    assert cfg.state_db_url == "sqlite:///./data/state.db"


def test_required_field_missing_raises(monkeypatch):
    with pytest.raises(Exception):
        _fresh_settings(
            monkeypatch,
            GEMINI_API_KEY="x",
            CONTROL_SHEET_URL="x",
            GOOGLE_CREDENTIALS_JSON="{}",
        )
