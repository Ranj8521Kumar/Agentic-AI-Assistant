"""
Base tool interface — all tools must implement this contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolDefinition(BaseModel):
    """Describes a tool to the agent and LLM."""
    name: str
    description: str
    provider: str          # gmail | slack | outlook | teams | calendar | jira | notion
    requires_confirmation: bool = False
    required_scopes: list[str] = []
    parameters: dict[str, Any] = {}   # JSON Schema for tool input

    def to_openai_function(self) -> dict[str, Any]:
        """Convert to OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class BaseTool(ABC):
    """
    Base class for all integration tools.
    Each tool must declare its definition and implement execute().
    """

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        ...

    @abstractmethod
    async def execute(
        self,
        arguments: dict[str, Any],
        user_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        """
        Execute the tool and return a structured result dict.
        Must raise ToolExecutionError on failure.
        """
        ...


class ToolExecutionError(Exception):
    """Raised when a tool fails to execute."""

    def __init__(self, tool_name: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.message = message
        self.retryable = retryable
