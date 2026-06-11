"""Shared-password access protection (single user)."""
import hashlib
import hmac
import os
from typing import Optional

_SALT = "emailmak-access-v1"


def _password() -> Optional[str]:
    pw = os.getenv("APP_PASSWORD")
    return pw or None


def protection_enabled() -> bool:
    return _password() is not None


def make_token(password: str) -> str:
    return hashlib.sha256((password + _SALT).encode()).hexdigest()


def expected_token() -> Optional[str]:
    pw = _password()
    return make_token(pw) if pw else None


def verify_token(token: str) -> bool:
    exp = expected_token()
    if exp is None:
        return False
    return hmac.compare_digest(token or "", exp)


def check_password(password: str) -> bool:
    pw = _password()
    return pw is not None and hmac.compare_digest(password or "", pw)
