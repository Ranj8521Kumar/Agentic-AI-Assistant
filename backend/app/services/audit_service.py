"""
Audit service — persists audit events for all significant platform actions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        action: str,
        outcome: str = "success",
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditEvent:
        """
        Persist an audit event.
        Never include raw tokens or secrets in metadata.
        """
        event = AuditEvent(
            action=action,
            outcome=outcome,
            user_id=user_id,
            workspace_id=workspace_id,
            event_metadata=metadata,
            ip_address=ip_address,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        await self.db.flush()
        return event
