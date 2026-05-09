"""Google Calendar tool definitions and implementations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError


class ScheduleMeetingTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="calendar_schedule_meeting",
            description=(
                "Schedule a Google Calendar meeting with optional Google Meet link. "
                "Provide attendee emails to invite them."
            ),
            provider="google",
            requires_confirmation=True,
            required_scopes=["https://www.googleapis.com/auth/calendar"],
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Meeting title"},
                    "start_time": {
                        "type": "string",
                        "description": "ISO 8601 start datetime, e.g. 2024-06-01T10:00:00",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes (default 60)",
                        "default": 60,
                    },
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee email addresses",
                    },
                    "description": {
                        "type": "string",
                        "description": "Meeting description or agenda",
                    },
                    "add_meet_link": {
                        "type": "boolean",
                        "description": "Add a Google Meet video link",
                        "default": True,
                    },
                },
                "required": ["title", "start_time"],
            },
        )

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        title = arguments["title"]
        start_str = arguments["start_time"]
        duration = int(arguments.get("duration_minutes", 60))
        attendees = arguments.get("attendees", [])
        description = arguments.get("description", "")
        add_meet = arguments.get("add_meet_link", True)

        try:
            start_dt = datetime.fromisoformat(start_str)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            end_dt = start_dt + timedelta(minutes=duration)

            event: dict[str, Any] = {
                "summary": title,
                "description": description,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
                "attendees": [{"email": e} for e in attendees],
            }
            if add_meet:
                event["conferenceData"] = {
                    "createRequest": {
                        "requestId": f"meet-{user_id}-{int(start_dt.timestamp())}",
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                }

            creds = Credentials(token=access_token)
            service = build("calendar", "v3", credentials=creds)
            created = service.events().insert(
                calendarId="primary",
                body=event,
                conferenceDataVersion=1 if add_meet else 0,
                sendUpdates="all" if attendees else "none",
            ).execute()

            meet_link = (
                created.get("conferenceData", {})
                .get("entryPoints", [{}])[0]
                .get("uri", "")
            )
            return {
                "success": True,
                "event_id": created.get("id"),
                "html_link": created.get("htmlLink"),
                "meet_link": meet_link,
                "summary": f"Meeting '{title}' scheduled for {start_dt.strftime('%Y-%m-%d %H:%M UTC')}.",
            }
        except Exception as e:
            raise ToolExecutionError("calendar_schedule_meeting", str(e), retryable=False)


class ListEventsTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="calendar_list_events",
            description="List upcoming events from Google Calendar.",
            provider="google",
            requires_confirmation=False,
            required_scopes=["https://www.googleapis.com/auth/calendar.readonly"],
            parameters={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Max events to return (default 10)",
                        "default": 10,
                    },
                    "time_min": {
                        "type": "string",
                        "description": "ISO 8601 start filter (default: now)",
                    },
                },
                "required": [],
            },
        )

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        max_results = min(int(arguments.get("max_results", 10)), 50)
        time_min = arguments.get("time_min") or datetime.now(timezone.utc).isoformat()

        try:
            creds = Credentials(token=access_token)
            service = build("calendar", "v3", credentials=creds)
            result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = [
                {
                    "id": e.get("id"),
                    "title": e.get("summary", "(no title)"),
                    "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                    "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
                    "attendees": [a.get("email") for a in e.get("attendees", [])],
                    "meet_link": next(
                        (ep.get("uri") for ep in e.get("conferenceData", {}).get("entryPoints", [])
                         if ep.get("entryPointType") == "video"),
                        None,
                    ),
                }
                for e in result.get("items", [])
            ]
            return {"success": True, "count": len(events), "events": events}
        except Exception as e:
            raise ToolExecutionError("calendar_list_events", str(e), retryable=True)
