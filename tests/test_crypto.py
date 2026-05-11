import pytest
from app.crypto import encrypt_secret, decrypt_secret, mask_secret


def test_encrypt_decrypt_roundtrip():
    plain = "sk-smartlead-abcdef1234567890"
    cipher = encrypt_secret(plain)
    assert cipher != plain
    assert decrypt_secret(cipher) == plain


def test_encrypt_produces_different_ciphertexts_each_call():
    plain = "the-same-secret"
    c1 = encrypt_secret(plain)
    c2 = encrypt_secret(plain)
    assert c1 != c2
    assert decrypt_secret(c1) == decrypt_secret(c2) == plain


def test_decrypt_garbage_raises():
    with pytest.raises(Exception):
        decrypt_secret("not-a-valid-fernet-token")


def test_mask_keeps_prefix_and_suffix():
    assert mask_secret("sk-abcdefghijklmnop") == "sk-a***mnop"
    assert mask_secret("short") == "***"
    assert mask_secret("") == ""
    assert mask_secret(None) == ""
