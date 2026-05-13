"""Outlook (Microsoft Graph) tool definitions."""

from __future__ import annotations

from typing import Any

import httpx

from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class SendOutlookEmailTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="outlook_send_email",
            description="Send an email via Microsoft Outlook / Exchange.",
            provider="microsoft",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body (HTML or plain text)"},
                },
                "required": ["to", "subject", "body"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        payload = {
            "message": {
                "subject": arguments["subject"],
                "body": {"contentType": "Text", "content": arguments["body"]},
                "toRecipients": [{"emailAddress": {"address": arguments["to"]}}],
            },
            "saveToSentItems": True,
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{GRAPH_BASE}/me/sendMail",
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if resp.status_code not in (200, 202):
                raise ToolExecutionError("outlook_send_email", f"Graph API error: {resp.text}")
            return {"success": True, "summary": f"Email sent to {arguments['to']}."}
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("outlook_send_email", str(e))


class ReadOutlookInboxTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="outlook_read_inbox",
            description="Read recent emails from the Outlook inbox.",
            provider="microsoft",
            requires_confirmation=False,
            parameters={
                "type": "object",
                "properties": {
                    "top": {"type": "integer", "description": "Number of emails (default 10)", "default": 10},
                },
                "required": [],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        top = min(int(arguments.get("top", 10)), 50)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GRAPH_BASE}/me/mailFolders/inbox/messages",
                    params={"$top": top, "$select": "subject,from,receivedDateTime,bodyPreview"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            resp.raise_for_status()
            emails = [
                {
                    "subject": m.get("subject", ""),
                    "from": m.get("from", {}).get("emailAddress", {}).get("address", ""),
                    "received": m.get("receivedDateTime", ""),
                    "preview": m.get("bodyPreview", ""),
                }
                for m in resp.json().get("value", [])
            ]
            return {"success": True, "count": len(emails), "emails": emails}
        except Exception as e:
            raise ToolExecutionError("outlook_read_inbox", str(e))
