"""
시크릿 암호화·마스킹 유틸.
APP_SECRET_KEY를 시드로 PBKDF2-HMAC-SHA256으로 Fernet 키 파생.
"""
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet

from app.config import get_settings


_FERNET: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is None:
        seed = get_settings().app_secret_key.encode("utf-8")
        key = hashlib.pbkdf2_hmac("sha256", seed, b"emailmak-fernet-v1", 100_000, dklen=32)
        _FERNET = Fernet(base64.urlsafe_b64encode(key))
    return _FERNET


def encrypt_secret(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def mask_secret(value: Optional[str]) -> str:
    if not value:
        return ""
    if len(value) < 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"
