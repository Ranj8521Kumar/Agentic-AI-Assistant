"""Microsoft Teams tool definitions."""

from __future__ import annotations

from typing import Any

import httpx

from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class CreateTeamsMeetingTool(BaseTool):
    """Create a Teams online meeting and return the join URL."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="teams_create_meeting",
            description=(
                "Create a Microsoft Teams online meeting (video call / interview). "
                "Returns a join URL that can be shared with participants. "
                "Use this when the user wants to schedule a Teams call, interview, or meeting. "
                "You do NOT need a team ID or channel ID — this creates a standalone meeting link."
            ),
            provider="microsoft",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Meeting title / subject",
                    },
                    "start_datetime": {
                        "type": "string",
                        "description": "Start date and time in ISO 8601 format (e.g. 2026-10-05T15:30:00)",
                    },
                    "end_datetime": {
                        "type": "string",
                        "description": "End date and time in ISO 8601 format (e.g. 2026-10-05T16:30:00)",
                    },
                    "attendee_emails": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee email addresses to invite",
                    },
                },
                "required": ["subject", "start_datetime", "end_datetime"],
            },
        )

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        subject = arguments["subject"]
        start_dt = arguments["start_datetime"]
        end_dt = arguments["end_datetime"]
        attendees = arguments.get("attendee_emails", [])

        # Ensure ISO format with timezone
        if not start_dt.endswith("Z") and "+" not in start_dt:
            start_dt += "Z"
        if not end_dt.endswith("Z") and "+" not in end_dt:
            end_dt += "Z"

        body: dict[str, Any] = {
            "subject": subject,
            "startDateTime": start_dt,
            "endDateTime": end_dt,
        }

        try:
            async with httpx.AsyncClient() as client:
                # Step 1: Create the online meeting
                resp = await client.post(
                    f"{GRAPH_BASE}/me/onlineMeetings",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                )
            resp.raise_for_status()
            data = resp.json()
            join_url = data.get("joinWebUrl", "")
            meeting_id = data.get("id", "")

            # Step 2: If attendees provided, send calendar invite via Outlook
            if attendees:
                event_body: dict[str, Any] = {
                    "subject": subject,
                    "start": {"dateTime": start_dt.rstrip("Z"), "timeZone": "UTC"},
                    "end": {"dateTime": end_dt.rstrip("Z"), "timeZone": "UTC"},
                    "isOnlineMeeting": True,
                    "onlineMeetingProvider": "teamsForBusiness",
                    "onlineMeeting": {"joinUrl": join_url},
                    "attendees": [
                        {
                            "emailAddress": {"address": email},
                            "type": "required",
                        }
                        for email in attendees
                    ],
                    "body": {
                        "contentType": "HTML",
                        "content": (
                            f"<p>You are invited to: <b>{subject}</b></p>"
                            f"<p>Join Teams Meeting: <a href='{join_url}'>{join_url}</a></p>"
                        ),
                    },
                }
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{GRAPH_BASE}/me/events",
                        json=event_body,
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                    )

            return {
                "success": True,
                "meeting_id": meeting_id,
                "join_url": join_url,
                "attendees_invited": len(attendees),
                "summary": (
                    f"Teams meeting '{subject}' created. Join URL: {join_url}. "
                    f"{len(attendees)} attendee(s) invited via calendar."
                ),
            }
        except Exception as e:
            raise ToolExecutionError("teams_create_meeting", str(e))


class SendTeamsMessageTool(BaseTool):
    """Send a 1-on-1 chat message or channel message on Teams."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="teams_send_message",
            description=(
                "Send a direct (1-on-1) message to a Microsoft Teams user by their email address. "
                "You do NOT need a team ID or channel ID for direct messages. "
                "If the user wants to send to a specific channel, they must provide team_id and channel_id."
            ),
            provider="microsoft",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "recipient_email": {
                        "type": "string",
                        "description": "Email of the person to message (for 1-on-1 DM)",
                    },
                    "message": {"type": "string", "description": "Message content"},
                    "team_id": {
                        "type": "string",
                        "description": "Teams team ID (only required for channel messages)",
                    },
                    "channel_id": {
                        "type": "string",
                        "description": "Teams channel ID (only required for channel messages)",
                    },
                },
                "required": ["message"],
            },
        )

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        message = arguments["message"]
        recipient_email = arguments.get("recipient_email")
        team_id = arguments.get("team_id")
        channel_id = arguments.get("channel_id")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                if team_id and channel_id:
                    # Channel message
                    resp = await client.post(
                        f"{GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/messages",
                        json={"body": {"content": message}},
                        headers=headers,
                    )
                elif recipient_email:
                    # 1-on-1 DM — first create/get the chat
                    chat_resp = await client.post(
                        f"{GRAPH_BASE}/chats",
                        json={
                            "chatType": "oneOnOne",
                            "members": [
                                {
                                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                                    "roles": ["owner"],
                                    "user@odata.bind": f"{GRAPH_BASE}/users/{recipient_email}",
                                },
                            ],
                        },
                        headers=headers,
                    )
                    chat_resp.raise_for_status()
                    chat_id = chat_resp.json()["id"]

                    resp = await client.post(
                        f"{GRAPH_BASE}/chats/{chat_id}/messages",
                        json={"body": {"content": message}},
                        headers=headers,
                    )
                else:
                    raise ToolExecutionError(
                        "teams_send_message",
                        "Provide either recipient_email (for DM) or both team_id and channel_id (for channel).",
                    )

            resp.raise_for_status()
            data = resp.json()
            return {
                "success": True,
                "message_id": data.get("id"),
                "summary": f"Teams message sent successfully.",
            }
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("teams_send_message", str(e))
