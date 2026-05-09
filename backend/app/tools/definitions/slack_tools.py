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
            description=(
                "Send a message to a Slack channel or a direct message to a user. "
                "For channels use #channel-name (e.g. #general). "
                "For DMs use @display-name or @username (e.g. @ankitpandit92054). "
                "You can also use the user's email address to find them."
            ),
            provider="slack",
            requires_confirmation=True,
            required_scopes=["chat:write"],
            parameters={
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel (#general) or user (@username or email) to DM",
                    },
                    "text": {"type": "string", "description": "Message text to send"},
                },
                "required": ["channel", "text"],
            },
        )

    async def _resolve_channel(self, client: Any, channel: str) -> str:
        """Resolve @username or email to a DM channel ID via conversations.open."""
        target = channel.lstrip("@").strip()

        # Try looking up by email first
        if "@" in target and "." in target:
            try:
                resp = await client.users_lookupByEmail(email=target)
                if resp["ok"]:
                    user_id = resp["user"]["id"]
                    dm = await client.conversations_open(users=[user_id])
                    return dm["channel"]["id"]
            except Exception:
                pass

        # Look up by display name / real name via users.list
        resp = await client.users_list()
        if resp["ok"]:
            for member in resp["members"]:
                profile = member.get("profile", {})
                names = [
                    member.get("name", ""),
                    profile.get("display_name", ""),
                    profile.get("real_name", ""),
                ]
                if any(target.lower() == n.lower() for n in names if n):
                    dm = await client.conversations_open(users=[member["id"]])
                    return dm["channel"]["id"]

        # If nothing matched, return as-is and let Slack API give the real error
        return channel

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        channel = arguments["channel"]
        text = arguments["text"]
        try:
            client = AsyncWebClient(token=access_token)

            # Resolve @username or email → DM channel ID
            if channel.startswith("@") or ("@" in channel and not channel.startswith("#")):
                channel = await self._resolve_channel(client, channel)

            result = await client.chat_postMessage(channel=channel, text=text)
            return {
                "success": True,
                "ts": result["ts"],
                "channel": result["channel"],
                "summary": f"Message sent successfully.",
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
