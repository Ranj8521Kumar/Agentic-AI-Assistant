"""
Chat API routes — handles message submission and SSE streaming.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import AgentOrchestrator, TOOL_EVENT_PREFIX
from app.db.session import get_db
from app.dependencies import get_current_user_id
from app.models.message import MessageRole
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["Chat"])


class SendMessageRequest(BaseModel):
    message: str
    conversation_id: uuid.UUID | None = None


async def _generate_title(message: str) -> str:
    """Use the LLM to produce a short conversation title from the first user message."""
    try:
        from app.llm.openai_provider import OpenAIProvider
        from app.llm.adapter import LLMMessage
        llm = OpenAIProvider()
        resp = await llm.complete(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are a title generator. Given the user's first message, "
                        "produce a short (4–6 word) title for the conversation. "
                        "Return ONLY the title text, no punctuation at the end, no quotes."
                    ),
                ),
                LLMMessage(role="user", content=message),
            ]
        )
        title = (resp.content or "").strip()
        # Truncate to 80 chars as safety net
        return title[:80] if title else "New Conversation"
    except Exception:
        return "New Conversation"


@router.post("/send", summary="Send a message and receive a streaming response")
async def send_message(
    request: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
) -> StreamingResponse:
    """
    Accepts a user message and returns a Server-Sent Events (SSE) stream.
    The stream contains:
      - data: __tool_event__:<JSON>  → tool execution events
      - data: <text chunk>           → final assistant answer tokens
      - data: [DONE]                 → stream complete signal
    """
    chat_service = ChatService(db)

    is_new_conversation = request.conversation_id is None
    conversation = await chat_service.get_or_create_conversation(
        user_id=current_user_id,
        conversation_id=request.conversation_id,
    )

    # Auto-generate a title for brand-new conversations
    if is_new_conversation:
        title = await _generate_title(request.message)
        conversation.title = title
        await db.flush()

    # Persist the user message
    await chat_service.add_message(
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content=request.message,
    )
    await db.commit()

    history = await chat_service.get_history(conversation.id, limit=50)

    async def event_stream():
        orchestrator = AgentOrchestrator(db)
        full_response_chunks = []

        async for chunk in orchestrator.run(
            user_id=current_user_id,
            conversation_id=conversation.id,
            user_message=request.message,
            history=history[:-1],  # exclude the just-added user message
        ):
            if chunk.startswith(TOOL_EVENT_PREFIX):
                yield f"data: {chunk}\n\n"
            else:
                full_response_chunks.append(chunk)
                yield f"data: {chunk}\n\n"

        # Persist the full assistant response
        full_response = "".join(full_response_chunks)
        if full_response:
            await chat_service.add_message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=full_response,
            )
            await db.commit()

        # Send conversation ID back then signal done
        yield f"data: __conversation_id__:{conversation.id}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", summary="List user's conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
):
    chat_service = ChatService(db)
    conversations = await chat_service.list_conversations(current_user_id)
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}/messages", summary="Get messages in a conversation")
async def get_messages(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID = Depends(get_current_user_id),
):
    chat_service = ChatService(db)
    messages = await chat_service.get_history(conversation_id, limit=100)
    return [
        {
            "id": str(m.id),
            "role": m.role.value,
            "content": m.content,
            "tool_calls": m.tool_calls,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]
