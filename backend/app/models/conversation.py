"""Conversation ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)

    # Fix #2 — use sa.text() for portable server_default instead of a raw string
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("false")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Fix #1 — onupdate lambda does NOT fire in async SQLAlchemy ORM sessions.
    # updated_at is set explicitly in the service layer on every mutation.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Fix #3 — workspace is nullable (workspace_id is Optional), reflect that in the type hint.
    # Fix #4 — declare lazy="noload" on all relationships to prevent accidental
    #           N+1 queries and DetachedInstanceError in async sessions.
    #           Use selectinload() / joinedload() explicitly at the call site when needed.
    # Fix #5 — removed unnecessary # noqa: F821 comments; `from __future__ import annotations`
    #           already makes all annotations lazy strings, so forward refs resolve fine.
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        back_populates="conversations", lazy="noload"
    )
    workspace: Mapped["Workspace | None"] = relationship(  # type: ignore[name-defined]
        back_populates="conversations", lazy="noload"
    )
    messages: Mapped[list["Message"]] = relationship(  # type: ignore[name-defined]
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="noload",
    )
