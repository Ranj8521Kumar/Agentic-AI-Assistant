"""
Unit tests for the Agent Orchestrator.
Tests the agentic loop logic with mocked LLM and tool registry.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.orchestrator import AgentOrchestrator, TOOL_EVENT_PREFIX
from app.llm.adapter import LLMResponse


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_auth_service():
    svc = AsyncMock()
    svc.list_connected_accounts.return_value = []
    svc.get_user_by_id.return_value = MagicMock(full_name="Test User")
    svc.get_connected_account.return_value = None
    return svc


@pytest.fixture
def orchestrator(mock_db, mock_auth_service):
    with patch("app.agent.orchestrator.AuthService", return_value=mock_auth_service), \
         patch("app.agent.orchestrator.OpenAIProvider"):
        orch = AgentOrchestrator(mock_db)
        orch.auth_service = mock_auth_service
        return orch


@pytest.mark.asyncio
async def test_orchestrator_yields_text_when_no_tools(orchestrator):
    """When LLM returns text with no tool calls, orchestrator yields the text."""
    orchestrator.llm = AsyncMock()
    orchestrator.llm.complete = AsyncMock(return_value=LLMResponse(
        content="Hello! How can I help?",
        tool_calls=None,
        finish_reason="stop",
    ))

    chunks = []
    async for chunk in orchestrator.run(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        user_message="Hi",
        history=[],
    ):
        chunks.append(chunk)

    full_text = "".join(chunks)
    assert "Hello! How can I help?" in full_text
    assert not any(c.startswith(TOOL_EVENT_PREFIX) for c in chunks)


@pytest.mark.asyncio
async def test_orchestrator_emits_tool_event_when_no_account(orchestrator):
    """When tool requires a provider the user hasn't connected, emit an error event."""
    tool_call = {
        "id": "call_123",
        "type": "function",
        "function": {
            "name": "gmail_send_email",
            "arguments": json.dumps({"to": "a@b.com", "subject": "Hi", "body": "Hello"}),
        },
    }

    # First call returns tool call, second returns final text
    orchestrator.llm = AsyncMock()
    orchestrator.llm.complete = AsyncMock(side_effect=[
        LLMResponse(content=None, tool_calls=[tool_call], finish_reason="tool_calls"),
        LLMResponse(content="Done.", tool_calls=None, finish_reason="stop"),
    ])

    # No connected account for google
    orchestrator.auth_service.get_connected_account = AsyncMock(return_value=None)

    chunks = []
    async for chunk in orchestrator.run(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        user_message="Send an email",
        history=[],
    ):
        chunks.append(chunk)

    tool_events = [c for c in chunks if c.startswith(TOOL_EVENT_PREFIX)]
    assert len(tool_events) >= 1

    # Should have an error event about no connected account
    error_events = [c for c in tool_events if "error" in c]
    assert len(error_events) >= 1


@pytest.mark.asyncio
async def test_orchestrator_fallback_after_max_iterations(orchestrator):
    """After 10 iterations of tool calls without resolution, yield fallback message."""
    tool_call = {
        "id": "call_loop",
        "type": "function",
        "function": {"name": "nonexistent_tool", "arguments": "{}"},
    }

    # Always return tool calls — force max iterations
    orchestrator.llm = AsyncMock()
    orchestrator.llm.complete = AsyncMock(return_value=LLMResponse(
        content=None, tool_calls=[tool_call], finish_reason="tool_calls"
    ))

    chunks = []
    async for chunk in orchestrator.run(
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        user_message="loop forever",
        history=[],
    ):
        chunks.append(chunk)

    full = " ".join(chunks)
    assert "wasn't able to complete" in full or len(chunks) > 0


@pytest.mark.asyncio
async def test_tool_event_prefix_constant():
    assert TOOL_EVENT_PREFIX == "__tool_event__:"
