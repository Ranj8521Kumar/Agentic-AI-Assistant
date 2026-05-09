"""Slack tool definitions and implementations."""

from __future__ import annotations

from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError


class SendSlackMessageTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="slack_send_message",
            description="Send a message to a Slack channel or DM.",
            provider="slack",
            requires_confirmation=True,
            required_scopes=["chat:write"],
            parameters={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name (e.g. #general) or user ID for DM",
                    },
                    "text": {"type": "string", "description": "Message text to send"},
                },
                "required": ["channel", "text"],
            },
        )

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        channel = arguments["channel"]
        text = arguments["text"]
        try:
            client = AsyncWebClient(token=access_token)
            result = await client.chat_postMessage(channel=channel, text=text)
            return {
                "success": True,
                "ts": result["ts"],
                "channel": result["channel"],
                "summary": f"Message sent to {channel}.",
            }
        except Exception as e:
            raise ToolExecutionError("slack_send_message", str(e), retryable=False)


class ReadSlackChannelTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="slack_read_channel",
            description="Read recent messages from a Slack channel.",
            provider="slack",
            requires_confirmation=False,
            required_scopes=["channels:read", "channels:history"],
            parameters={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name or ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of messages to fetch (default 20)",
                        "default": 20,
                    },
                },
                "required": ["channel"],
            },
        )

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        channel = arguments["channel"]
        limit = min(int(arguments.get("limit", 20)), 100)
        try:
            client = AsyncWebClient(token=access_token)
            result = await client.conversations_history(channel=channel, limit=limit)
            messages = [
                {
                    "user": msg.get("user", "unknown"),
                    "text": msg.get("text", ""),
                    "ts": msg.get("ts", ""),
                }
                for msg in result.get("messages", [])
            ]
            return {"success": True, "count": len(messages), "messages": messages}
        except Exception as e:
            raise ToolExecutionError("slack_read_channel", str(e), retryable=True)
