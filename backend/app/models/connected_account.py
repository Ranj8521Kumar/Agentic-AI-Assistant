"""ConnectedAccount ORM model — stores encrypted OAuth tokens per provider."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ConnectedAccount(Base):
    """
    Stores a connected OAuth account for a user.
    Tokens are stored encrypted using Fernet symmetric encryption.
    """

    __tablename__ = "connected_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Provider: google | microsoft | slack | jira | notion
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    # Provider-specific user/account identifier
    provider_account_id: Mapped[str | None] = mapped_column(String(255))
    provider_email: Mapped[str | None] = mapped_column(String(255))

    # Encrypted token fields (Fernet encrypted at rest)
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Provider-specific scopes granted
    scopes: Mapped[str | None] = mapped_column(Text)  # space-separated

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="connected_accounts")  # noqa: F821

    def __repr__(self) -> str:
        return f"<ConnectedAccount user={self.user_id} provider={self.provider}>"
