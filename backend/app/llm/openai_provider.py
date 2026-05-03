"""
OpenAI GPT provider implementation.
Supports both structured completion and streaming.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from app.config import settings
from app.llm.adapter import BaseLLMAdapter, LLMMessage, LLMResponse


class OpenAIProvider(BaseLLMAdapter):
    """OpenAI GPT provider using the official async client."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = settings.OPENAI_MODEL

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """Convert internal LLMMessage objects to OpenAI format."""
        result = []
        for msg in messages:
            m: dict[str, Any] = {"role": msg.role}
            if msg.content is not None:
                m["content"] = msg.content
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.name:
                m["name"] = msg.name
            result.append(m)
        return result

    async def complete(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict = "auto",
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": self._convert_messages(messages),
            "max_tokens": settings.OPENAI_MAX_TOKENS,
            "temperature": settings.OPENAI_TEMPERATURE,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": self._convert_messages(messages),
            "max_tokens": settings.OPENAI_MAX_TOKENS,
            "temperature": settings.OPENAI_TEMPERATURE,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        async with self._client.chat.completions.stream(**kwargs) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
