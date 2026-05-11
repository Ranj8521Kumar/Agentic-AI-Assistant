"""Gmail tool definitions and implementations."""

from __future__ import annotations

import base64
import json
from email.mime.text import MIMEText
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError
from app.config import settings


class SendEmailTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="gmail_send_email",
            description="Send an email via Gmail on behalf of the user.",
            provider="google",
            requires_confirmation=True,
            required_scopes=["https://www.googleapis.com/auth/gmail.send"],
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Plain text email body"},
                    "cc": {"type": "string", "description": "CC email address (optional)"},
                },
                "required": ["to", "subject", "body"],
            },
        )

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        to = arguments["to"]
        subject = arguments["subject"]
        body = arguments["body"]
        cc = arguments.get("cc")

        try:
            creds = Credentials(
                token=access_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
            )
            service = build("gmail", "v1", credentials=creds)

            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject
            if cc:
                message["cc"] = cc

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            result = service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()

            return {
                "success": True,
                "message_id": result.get("id"),
                "summary": f"Email sent to {to} with subject '{subject}'.",
            }
        except Exception as e:
            raise ToolExecutionError("gmail_send_email", str(e), retryable=False)


class ReadInboxTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="gmail_read_inbox",
            description="Read recent emails from the Gmail inbox.",
            provider="google",
            requires_confirmation=False,
            required_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            parameters={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Number of emails to fetch (default 10, max 50)",
                        "default": 10,
                    },
                    "query": {
                        "type": "string",
                        "description": "Gmail search query (e.g. 'from:someone@example.com')",
                    },
                },
                "required": [],
            },
        )

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        max_results = min(int(arguments.get("max_results", 10)), 50)
        query = arguments.get("query", "")

        try:
            creds = Credentials(
                token=access_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
            )
            service = build("gmail", "v1", credentials=creds)

            list_result = service.users().messages().list(
                userId="me",
                maxResults=max_results,
                q=query or "in:inbox",
            ).execute()

            messages = list_result.get("messages", [])
            emails = []
            for msg_ref in messages:
                msg = service.users().messages().get(
                    userId="me", id=msg_ref["id"], format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                emails.append({
                    "id": msg["id"],
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", "(no subject)"),
                    "date": headers.get("Date", ""),
                    "snippet": msg.get("snippet", ""),
                })

            return {"success": True, "count": len(emails), "emails": emails}
        except Exception as e:
            raise ToolExecutionError("gmail_read_inbox", str(e), retryable=True)


class ReadThreadTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="gmail_read_thread",
            description="Read a full email thread by thread ID.",
            provider="google",
            requires_confirmation=False,
            required_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            parameters={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "Gmail thread ID"},
                },
                "required": ["thread_id"],
            },
        )

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        thread_id = arguments["thread_id"]
        try:
            creds = Credentials(
                token=access_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
            )
            service = build("gmail", "v1", credentials=creds)
            thread = service.users().threads().get(
                userId="me", id=thread_id, format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            messages = []
            for msg in thread.get("messages", []):
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                messages.append({
                    "id": msg["id"],
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "snippet": msg.get("snippet", ""),
                })
            return {"success": True, "thread_id": thread_id, "messages": messages}
        except Exception as e:
            raise ToolExecutionError("gmail_read_thread", str(e), retryable=True)
