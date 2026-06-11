import auth


def test_protection_disabled_when_no_password(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    assert auth.protection_enabled() is False
    assert auth.verify_token("anything") is False
    assert auth.expected_token() is None


def test_make_and_verify_token(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    token = auth.make_token("secret123")
    assert auth.protection_enabled() is True
    assert auth.verify_token(token) is True
    assert auth.verify_token("wrong") is False


def test_check_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    assert auth.check_password("secret123") is True
    assert auth.check_password("nope") is False


def test_token_changes_with_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "a")
    token_a = auth.make_token("a")
    monkeypatch.setenv("APP_PASSWORD", "b")
    assert auth.verify_token(token_a) is False
