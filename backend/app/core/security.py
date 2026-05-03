"""
Security utilities: JWT creation/verification and Fernet token encryption.
Tokens stored in the database are always encrypted at rest.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.config import settings


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """Create a long-lived JWT refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.
    Raises jose.JWTError on invalid/expired tokens.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ── Fernet token vault ───────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    """Return a Fernet instance using the configured key."""
    key = settings.FERNET_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_token(plaintext: str) -> str:
    """Encrypt a plaintext OAuth token for storage."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt an OAuth token retrieved from storage."""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
