"""
FastAPI dependencies: database session, Redis, current user extraction.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decode_token
from app.db.session import get_db  # noqa: F401 — re-exported for convenience

_bearer = HTTPBearer(auto_error=False)

# ── Redis dependency ──────────────────────────────────────────────────────────

_redis_pool: AsyncRedis | None = None


async def get_redis() -> AsyncRedis:  # type: ignore[return]
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_pool


# ── Auth dependency ───────────────────────────────────────────────────────────

async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> uuid.UUID:
    """
    Extract and validate the Bearer JWT, returning the authenticated user ID.
    Raises HTTP 401 on missing or invalid tokens.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise ValueError("Missing subject claim")
        return uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
