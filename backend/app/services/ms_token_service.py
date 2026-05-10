"""
Microsoft token refresh service.

When a stored Microsoft access token is expired (or close to expiry), this
service exchanges the stored refresh token for a new access + refresh token
pair and persists both back to the database via AuthService.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import settings

log = logging.getLogger(__name__)


async def refresh_microsoft_token(
    auth_service,  # AuthService — avoids circular import
    account,       # ConnectedAccount model instance
) -> str:
    """
    Return a valid Microsoft access token for *account*.

    If the token expires within the next 5 minutes (or is already expired),
    attempt a refresh using the stored refresh token. The refreshed tokens are
    persisted back to the DB so subsequent calls reuse them.

    Returns the (possibly refreshed) plaintext access token.
    Raises RuntimeError if refresh fails.
    """
    from app.services.token_vault import token_vault

    # ── Decrypt current tokens ────────────────────────────────────────────────
    access_token = token_vault.retrieve(account.encrypted_access_token)
    refresh_token = token_vault.safe_retrieve(account.encrypted_refresh_token)

    # ── Check expiry ──────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    expires_at = account.token_expires_at
    # Treat naive datetimes as UTC
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    token_is_stale = (
        expires_at is None
        or expires_at <= now + timedelta(minutes=5)
    )

    if not token_is_stale:
        return access_token  # still valid — use as-is

    # ── Token is expired / near-expiry → refresh ──────────────────────────────
    if not refresh_token:
        raise RuntimeError(
            "Microsoft access token is expired and no refresh token is stored. "
            "Please reconnect your Microsoft / Outlook account in Settings."
        )

    log.info("Microsoft access token expired — refreshing for account %s", account.id)

    tenant_id = settings.MICROSOFT_TENANT_ID
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_url,
            data={
                "client_id": settings.MICROSOFT_CLIENT_ID,
                "client_secret": settings.MICROSOFT_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": " ".join(settings.MICROSOFT_SCOPES),
            },
        )

    if resp.status_code != 200:
        log.error("Microsoft token refresh failed: %s", resp.text)
        raise RuntimeError(
            f"Microsoft token refresh failed ({resp.status_code}). "
            "Please reconnect your Microsoft account in Settings & Integrations."
        )

    token_data = resp.json()
    new_access_token: str = token_data["access_token"]
    new_refresh_token: str | None = token_data.get("refresh_token", refresh_token)
    expires_in: int = token_data.get("expires_in", 3600)
    new_expires_at = now + timedelta(seconds=expires_in)

    # ── Persist refreshed tokens ───────────────────────────────────────────────
    await auth_service.upsert_connected_account(
        user_id=account.user_id,
        provider=account.provider,
        provider_account_id=account.provider_account_id,
        provider_email=account.provider_email,
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_expires_at=new_expires_at,
        scopes=account.scopes,
    )

    log.info("Microsoft access token refreshed successfully for account %s", account.id)
    return new_access_token
