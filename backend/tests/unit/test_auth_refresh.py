"""
Unit tests for the JWT refresh flow and auth token utilities.
"""
from __future__ import annotations

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)


def test_refresh_token_has_correct_type():
    token = create_refresh_token("user-123")
    payload = decode_token(token)
    assert payload["type"] == "refresh"
    assert payload["sub"] == "user-123"


def test_access_token_has_correct_type():
    token = create_access_token("user-456")
    payload = decode_token(token)
    assert payload["type"] == "access"
    assert payload["sub"] == "user-456"


def test_refresh_token_cannot_be_used_as_access():
    """A refresh token should have type='refresh', not 'access'."""
    refresh = create_refresh_token("user-789")
    payload = decode_token(refresh)
    assert payload["type"] != "access"


def test_access_token_cannot_be_used_as_refresh():
    """An access token should have type='access', not 'refresh'."""
    access = create_access_token("user-789")
    payload = decode_token(access)
    assert payload["type"] != "refresh"


def test_decode_tampered_token_raises():
    token = create_access_token("user-999")
    # Corrupt the signature by changing the last char
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(JWTError):
        decode_token(tampered)


def test_extra_claims_in_access_token():
    token = create_access_token("user-111", extra_claims={"role": "admin"})
    payload = decode_token(token)
    assert payload["role"] == "admin"
    assert payload["sub"] == "user-111"
