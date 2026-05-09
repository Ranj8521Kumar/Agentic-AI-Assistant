"""Unit tests for JWT and token vault security helpers."""

import pytest
from jose import JWTError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    encrypt_token,
    decrypt_token,
)
from app.config import settings
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def patch_fernet_key(monkeypatch):
    """Use a real Fernet key for tests."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "FERNET_KEY", key)


def test_access_token_roundtrip():
    user_id = "test-user-123"
    token = create_access_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    user_id = "test-user-456"
    token = create_refresh_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"


def test_invalid_token_raises():
    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")


def test_token_encryption_roundtrip():
    plaintext = "my-super-secret-oauth-token"
    encrypted = encrypt_token(plaintext)
    assert encrypted != plaintext
    assert decrypt_token(encrypted) == plaintext


def test_different_encryptions_are_unique():
    plaintext = "same-token"
    enc1 = encrypt_token(plaintext)
    enc2 = encrypt_token(plaintext)
    # Fernet includes a timestamp, so each encryption is different
    assert enc1 != enc2
    # But both decrypt correctly
    assert decrypt_token(enc1) == plaintext
    assert decrypt_token(enc2) == plaintext
