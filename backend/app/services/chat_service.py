"""
Chat service — manages conversations and message persistence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole


class ChatService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_conversation(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
        title: str | None = None,
    ) -> Conversation:
        if conversation_id:
            result = await self.db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            convo = result.scalar_one_or_none()
            if convo:
                return convo

        convo = Conversation(
            user_id=user_id,
            title=title or "New Conversation",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(convo)
        await self.db.flush()
        return convo

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: str | None,
        tool_calls: list | None = None,
        tool_call_id: str | None = None,
    ) -> Message:
        now = datetime.now(timezone.utc)
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            created_at=now,
        )
        self.db.add(msg)
        await self.db.flush()

        # Bump conversation updated_at explicitly — onupdate lambda is unreliable
        # in async SQLAlchemy ORM sessions (see conversation.py Issue #1).
        await self.db.execute(
            sa.update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=now)
        )
        return msg

    async def get_history(
        self, conversation_id: uuid.UUID, limit: int = 50
    ) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_conversations(self, user_id: uuid.UUID) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc())
            .limit(100)
        )
        return list(result.scalars().all())

    async def delete_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Hard-delete a conversation. Returns True if found and deleted."""
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        convo = result.scalar_one_or_none()
        if not convo:
            return False
        await self.db.delete(convo)
        return True

    async def rename_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, title: str
    ) -> Conversation | None:
        """Rename a conversation title. Returns updated conversation or None."""
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        convo = result.scalar_one_or_none()
        if not convo:
            return None
        convo.title = title[:255]  # respect column length
        convo.updated_at = datetime.now(timezone.utc)  # explicit — onupdate won't fire
        await self.db.flush()
        return convo

    async def toggle_pin(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, pinned: bool
    ) -> Conversation | None:
        """Pin or unpin a conversation. Returns updated conversation or None."""
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        convo = result.scalar_one_or_none()
        if not convo:
            return None
        convo.is_pinned = pinned
        convo.updated_at = datetime.now(timezone.utc)  # explicit — onupdate won't fire
        await self.db.flush()
        return convo
