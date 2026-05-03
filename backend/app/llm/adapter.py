"""
LLM Adapter — abstract interface for language model providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str  # system | user | assistant | tool
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    finish_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


class BaseLLMAdapter(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict = "auto",
    ) -> LLMResponse:
        """Send messages to the LLM and return the response."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Stream the LLM response token by token."""
        ...
