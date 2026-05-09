"""
Background jobs API — enqueue delayed or scheduled tasks.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.dependencies import get_current_user_id

router = APIRouter(prefix="/jobs", tags=["Background Jobs"])


class ScheduledEmailRequest(BaseModel):
    provider: str        # "google" or "microsoft"
    to: str
    subject: str
    body: str
    send_at: datetime    # ISO 8601 UTC datetime


class ScheduledMeetingRequest(BaseModel):
    title: str
    start_time: datetime
    attendees: list[str] = []
    duration_minutes: int = 60


async def _get_arq_pool():
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))


@router.post("/schedule-email", summary="Schedule an email to be sent later")
async def schedule_email(
    req: ScheduledEmailRequest,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> JSONResponse:
    """Enqueue a delayed email send job."""
    try:
        pool = await _get_arq_pool()
        job = await pool.enqueue_job(
            "send_scheduled_email",
            str(current_user_id),
            req.provider,
            req.to,
            req.subject,
            req.body,
            _defer_until=req.send_at,
        )
        return JSONResponse({
            "job_id": job.job_id if job else None,
            "scheduled_for": req.send_at.isoformat(),
            "status": "queued",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue job: {e}")


@router.post("/schedule-meeting", summary="Schedule a calendar meeting creation later")
async def schedule_meeting(
    req: ScheduledMeetingRequest,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> JSONResponse:
    """Enqueue a delayed Google Calendar event creation."""
    try:
        pool = await _get_arq_pool()
        job = await pool.enqueue_job(
            "create_scheduled_meeting",
            str(current_user_id),
            req.title,
            req.start_time.isoformat(),
            req.attendees,
            req.duration_minutes,
        )
        return JSONResponse({
            "job_id": job.job_id if job else None,
            "status": "queued",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue job: {e}")
