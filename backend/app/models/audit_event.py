"""AuditEvent ORM model — immutable log of all significant platform actions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Action type e.g. "gmail.send_email", "slack.send_message", "auth.login"
    action: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    # Outcome: success | failure | blocked | confirmation_required
    outcome: Mapped[str] = mapped_column(String(50), nullable=False, default="success")

    # Arbitrary JSON payload — NEVER store raw secrets here
    event_metadata: Mapped[dict | None] = mapped_column(JSONB, name="metadata")

    # Network context
    ip_address: Mapped[str | None] = mapped_column(String(45))  # IPv6 max length

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
