"""
ARQ Background Worker — handles scheduled and async tasks.
Run with: python -m app.jobs.worker
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.config import settings


# ── Task functions ────────────────────────────────────────────────────────────

async def send_scheduled_email(
    ctx: dict,
    user_id: str,
    provider: str,
    to: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """
    Delayed email send — enqueued when the user says "send this email tomorrow".
    Retrieves the token from the vault and dispatches via the Gmail/Outlook adapter.
    """
    from app.db.session import AsyncSessionLocal
    from app.services.auth_service import AuthService
    from app.services.token_vault import token_vault
    from app.tools.registry import registry

    async with AsyncSessionLocal() as db:
        auth = AuthService(db)
        account = await auth.get_connected_account(uuid.UUID(user_id), provider)
        if not account or not account.encrypted_access_token:
            return {"error": f"No connected {provider} account for user {user_id}"}

        access_token = token_vault.retrieve(account.encrypted_access_token)
        tool_name = "gmail_send_email" if provider == "google" else "outlook_send_email"
        tool = registry.get(tool_name)
        if not tool:
            return {"error": f"Tool {tool_name} not found"}

        result = await tool.execute(
            arguments={"to": to, "subject": subject, "body": body},
            user_id=user_id,
            access_token=access_token,
        )
        return result


async def create_scheduled_meeting(
    ctx: dict,
    user_id: str,
    title: str,
    start_time: str,
    attendees: list[str],
    duration_minutes: int = 60,
) -> dict[str, Any]:
    """Delayed calendar event creation."""
    from app.db.session import AsyncSessionLocal
    from app.services.auth_service import AuthService
    from app.services.token_vault import token_vault
    from app.tools.registry import registry

    async with AsyncSessionLocal() as db:
        auth = AuthService(db)
        account = await auth.get_connected_account(uuid.UUID(user_id), "google")
        if not account or not account.encrypted_access_token:
            return {"error": "No Google account connected"}

        access_token = token_vault.retrieve(account.encrypted_access_token)
        tool = registry.get("calendar_schedule_meeting")
        if not tool:
            return {"error": "Calendar tool not found"}

        result = await tool.execute(
            arguments={
                "title": title,
                "start_time": start_time,
                "attendees": attendees,
                "duration_minutes": duration_minutes,
                "add_meet_link": True,
            },
            user_id=user_id,
            access_token=access_token,
        )
        return result


async def cleanup_old_sessions(ctx: dict) -> dict[str, Any]:
    """
    Periodic job: removes Redis session keys older than 24h.
    Scheduled via cron — runs every hour.
    """
    redis = ctx.get("redis")
    if redis is None:
        return {"skipped": True}
    # Pattern: session:<user_id>
    keys = await redis.keys("session:*")
    cleaned = 0
    for key in keys:
        ttl = await redis.ttl(key)
        if ttl < 0:  # no expiry set — clean up orphan
            await redis.delete(key)
            cleaned += 1
    return {"cleaned_sessions": cleaned, "checked": len(keys)}


# ── Worker startup / shutdown ─────────────────────────────────────────────────

async def startup(ctx: dict) -> None:
    """Bootstrap the tool registry on worker startup."""
    from app.tools.registry import bootstrap_registry
    bootstrap_registry()


async def shutdown(ctx: dict) -> None:
    pass


# ── ARQ worker settings ───────────────────────────────────────────────────────

class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [
        send_scheduled_email,
        create_scheduled_meeting,
        cleanup_old_sessions,
    ]
    cron_jobs = [
        cron(cleanup_old_sessions, hour=None, minute=0),  # every hour on the :00
    ]
    on_startup = startup
    on_shutdown = shutdown
    job_timeout = settings.JOB_TIMEOUT_SECONDS
    max_jobs = 20


if __name__ == "__main__":
    import arq
    arq.run_worker(WorkerSettings)  # type: ignore[attr-defined]
