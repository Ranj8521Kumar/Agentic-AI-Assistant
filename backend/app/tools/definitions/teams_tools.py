"""Microsoft Teams tool definitions."""

from __future__ import annotations

from typing import Any

import httpx

from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class SendTeamsMessageTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="teams_send_message",
            description="Send a message to a Microsoft Teams channel or chat.",
            provider="microsoft",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "team_id": {"type": "string", "description": "Teams team ID"},
                    "channel_id": {"type": "string", "description": "Teams channel ID"},
                    "message": {"type": "string", "description": "Message content"},
                },
                "required": ["team_id", "channel_id", "message"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str) -> dict[str, Any]:
        team_id = arguments["team_id"]
        channel_id = arguments["channel_id"]
        message = arguments["message"]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/messages",
                    json={"body": {"content": message}},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "message_id": data.get("id"), "summary": "Teams message sent."}
        except Exception as e:
            raise ToolExecutionError("teams_send_message", str(e))
