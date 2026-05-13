"""Google Calendar tool definitions and implementations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError
from app.config import settings


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

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        import base64
        from email.mime.text import MIMEText

        title = arguments["title"]
        start_str = arguments["start_time"]
        duration = int(arguments.get("duration_minutes", 60))
        attendees = arguments.get("attendees", [])
        description = arguments.get("description", "")
        add_meet = arguments.get("add_meet_link", True)

        try:
            IST = timezone(timedelta(hours=5, minutes=30))
            start_dt = datetime.fromisoformat(start_str)
            if start_dt.tzinfo is None:
                # Treat bare datetimes from LLM as IST (user's local timezone)
                start_dt = start_dt.replace(tzinfo=IST)
            end_dt = start_dt + timedelta(minutes=duration)

            creds = Credentials(
                token=access_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
            )
            cal_service = build("calendar", "v3", credentials=creds)

            # ── Resolve organizer email from primary calendar ──────────────
            primary_cal = cal_service.calendars().get(calendarId="primary").execute()
            organizer_email: str = primary_cal.get("id", "")

            # Build deduplicated attendee list; always include organizer so
            # Google sends them an invitation email too.
            seen: set[str] = set()
            all_attendees: list[str] = []
            for email in ([organizer_email] + list(attendees)):
                lower = email.strip().lower()
                if lower and lower not in seen:
                    seen.add(lower)
                    all_attendees.append(email.strip())

            event: dict[str, Any] = {
                "summary": title,
                "description": description,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
                "attendees": [{"email": e} for e in all_attendees],
            }
            if add_meet:
                event["conferenceData"] = {
                    "createRequest": {
                        "requestId": f"meet-{user_id}-{int(start_dt.timestamp())}",
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                }

            created = cal_service.events().insert(
                calendarId="primary",
                body=event,
                conferenceDataVersion=1 if add_meet else 0,
                sendUpdates="all",   # sends invitations to ALL attendees incl. organizer
            ).execute()

            meet_link = (
                created.get("conferenceData", {})
                .get("entryPoints", [{}])[0]
                .get("uri", "")
            )
            html_link = created.get("htmlLink", "")
            start_fmt = start_dt.strftime("%Y-%m-%d %H:%M IST")

            # ── Send Gmail emails to organizer + all external attendees ───────
            # Reason 1: Google's sendUpdates silently skips the organizer.
            # Reason 2: Google sometimes throttles/filters calendar invites to
            #           free Gmail accounts — a direct email ensures delivery.
            try:
                gmail_service = build("gmail", "v1", credentials=creds)
                external_attendees = [
                    e for e in all_attendees if e.lower() != organizer_email.lower()
                ]
                attendee_list_str = "\n".join(
                    f"  • {e}" for e in external_attendees
                ) or "  (no external attendees)"

                def _build_body(recipient_role: str) -> str:
                    lines = [
                        f"You have been {'invited to' if recipient_role == 'attendee' else 'scheduled'} the following meeting.",
                        "",
                        f"Title    : {title}",
                        f"When     : {start_fmt} ({duration} minutes)",
                        f"Attendees:",
                        attendee_list_str,
                    ]
                    if meet_link:
                        lines += ["", f"Google Meet : {meet_link}"]
                    if html_link:
                        lines += [f"Calendar    : {html_link}"]
                    if description:
                        lines += ["", f"Description : {description}"]
                    return "\n".join(lines)

                # Email the organizer (confirmation)
                for to_email, role in (
                    [(organizer_email, "organizer")]
                    + [(e, "attendee") for e in external_attendees]
                ):
                    subject = (
                        f"Meeting Scheduled: {title} on {start_fmt}"
                        if role == "organizer"
                        else f"Meeting Invitation: {title} on {start_fmt}"
                    )
                    mime_msg = MIMEText(_build_body(role))
                    mime_msg["to"] = to_email
                    mime_msg["subject"] = subject
                    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
                    gmail_service.users().messages().send(
                        userId="me", body={"raw": raw}
                    ).execute()
            except Exception:
                # Email sending is best-effort; don't fail the whole tool
                pass


            return {
                "success": True,
                "event_id": created.get("id"),
                "html_link": html_link,
                "meet_link": meet_link,
                "organizer_email": organizer_email,
                "all_attendees": all_attendees,
                "summary": (
                    f"Meeting '{title}' scheduled for {start_fmt}. "
                    f"Invitations sent to {len(all_attendees)} participant(s) "
                    f"including you ({organizer_email})."
                ),
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

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        max_results = min(int(arguments.get("max_results", 10)), 50)
        time_min = arguments.get("time_min") or datetime.now(timezone.utc).isoformat()

        try:
            creds = Credentials(
                token=access_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
            )
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
