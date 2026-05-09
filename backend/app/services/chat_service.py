"""
Chat service — manages conversations and message persistence.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(msg)
        await self.db.flush()
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
            .order_by(Conversation.updated_at.desc())
            .limit(50)
        )
        return list(result.scalars().all())
