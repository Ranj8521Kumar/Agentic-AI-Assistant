"""Microsoft Teams tool definitions."""

from __future__ import annotations

import re
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

        # ── Robust datetime normalisation ──────────────────────────────────────
        # Microsoft Graph requires: "YYYY-MM-DDTHH:MM:SS" (no trailing Z for events)
        def normalise_dt(raw: str, keep_z: bool = False) -> str:
            from datetime import datetime as dt
            raw = raw.strip()
            raw_clean = raw.rstrip("Z").split("+")[0].split("-0")[0] if "T" in raw else raw

            formats = [
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%I:%M %p",
                "%Y-%m-%d %I:%M %p",
                "%Y-%m-%dT%I:%M:%S %p",
                "%d/%m/%YT%H:%M",
                "%d/%m/%Y %H:%M",
                "%m/%d/%YT%H:%M",
                "%m/%d/%Y %H:%M",
                "%Y-%m-%d",
            ]
            for fmt in formats:
                try:
                    parsed = dt.strptime(raw_clean, fmt)
                    if keep_z:
                        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
                    return parsed.strftime("%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    continue
            # Last resort
            return raw.rstrip("Z") if not keep_z else (raw if raw.endswith("Z") else raw + "Z")

        # For /me/events the dateTime must NOT have a trailing Z (timeZone field handles it)
        start_dt_plain = normalise_dt(start_dt, keep_z=False)
        end_dt_plain   = normalise_dt(end_dt,   keep_z=False)
        # For /me/onlineMeetings (fallback) Graph wants the Z suffix
        start_dt_z = start_dt_plain + "Z"
        end_dt_z   = end_dt_plain   + "Z"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # ── Strategy 1: /me/events with isOnlineMeeting (preferred) ───────────
        # Uses Calendars.ReadWrite — no admin consent required.
        # Graph auto-generates a Teams join URL when isOnlineMeeting=True.
        event_body: dict[str, Any] = {
            "subject": subject,
            "start": {"dateTime": start_dt_plain, "timeZone": "UTC"},
            "end":   {"dateTime": end_dt_plain,   "timeZone": "UTC"},
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness",
            "attendees": [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in attendees
            ],
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{GRAPH_BASE}/me/events",
                    json=event_body,
                    headers=headers,
                )

            # ── 401 = token expired or missing scopes → reconnect required ────
            if resp.status_code == 401:
                raise ToolExecutionError(
                    "teams_create_meeting",
                    (
                        "Your Microsoft account token has expired or is missing required permissions. "
                        "Please go to Settings & Integrations → Outlook / Teams → "
                        "Disconnect, then reconnect your account to refresh the token."
                    ),
                )

            if resp.is_success:
                data = resp.json()
                # Prefer the Teams join URL; fall back to the Outlook web link
                join_url = (
                    (data.get("onlineMeeting") or {}).get("joinUrl", "")
                    or data.get("webLink", "")
                )
                event_id = data.get("id", "")

                # ── Explicitly email each attendee ────────────────────────────
                # Calendar invites can silently fail across tenants (e.g. personal
                # account → org/edu account). Sending a direct email guarantees
                # delivery with all meeting details.
                email_errors: list[str] = []
                if attendees:
                    for attendee_email in attendees:
                        mail_body: dict[str, Any] = {
                            "message": {
                                "subject": f"Meeting Invitation: {subject}",
                                "body": {
                                    "contentType": "HTML",
                                    "content": (
                                        f"<p>Hello,</p>"
                                        f"<p>You have been invited to the following meeting:</p>"
                                        f"<table style='border-collapse:collapse;font-family:Arial,sans-serif'>"
                                        f"<tr><td style='padding:6px 12px;font-weight:bold'>Title</td>"
                                        f"<td style='padding:6px 12px'>{subject}</td></tr>"
                                        f"<tr><td style='padding:6px 12px;font-weight:bold'>Date &amp; Time</td>"
                                        f"<td style='padding:6px 12px'>{start_dt_plain} UTC – {end_dt_plain} UTC</td></tr>"
                                        f"<tr><td style='padding:6px 12px;font-weight:bold'>Join Link</td>"
                                        f"<td style='padding:6px 12px'>"
                                        f"<a href='{join_url}'>Click here to join the meeting</a>"
                                        f"</td></tr>"
                                        f"</table>"
                                        f"<br><p><b>Note:</b> You may be asked to sign in with a Microsoft account. "
                                        f"If you don't have one, click <b>'Join as a guest'</b> on the login page "
                                        f"to enter the meeting directly from your browser — no account required.</p>"
                                        f"<p>Please add this to your calendar.</p>"
                                    ),
                                },
                                "toRecipients": [
                                    {"emailAddress": {"address": attendee_email}}
                                ],
                            },
                            "saveToSentItems": "true",
                        }
                        async with httpx.AsyncClient() as client:
                            mail_resp = await client.post(
                                f"{GRAPH_BASE}/me/sendMail",
                                json=mail_body,
                                headers=headers,
                            )
                        if not mail_resp.is_success:
                            try:
                                merr = mail_resp.json().get("error", {})
                                email_errors.append(
                                    f"{attendee_email}: {merr.get('message', mail_resp.text)}"
                                )
                            except Exception:
                                email_errors.append(f"{attendee_email}: {mail_resp.text}")

                email_note = (
                    f" Email invitations sent to {len(attendees)} attendee(s)."
                    if not email_errors
                    else f" Email delivery failed for: {'; '.join(email_errors)}"
                )

                return {
                    "success": True,
                    "meeting_id": event_id,
                    "join_url": join_url,
                    "attendees_invited": len(attendees),
                    "email_errors": email_errors,
                    "summary": (
                        f"Teams meeting '{subject}' created successfully. "
                        f"Join URL: {join_url}. "
                        f"{email_note}"
                    ),
                }

            # Capture Strategy 1 error for combined error reporting
            try:
                err1 = resp.json().get("error", {})
                s1_detail = f"{err1.get('code', '')}: {err1.get('message', resp.text)}"
            except Exception:
                s1_detail = resp.text

            # ── Strategy 2: /me/onlineMeetings (fallback) ─────────────────────
            # Requires OnlineMeetings.ReadWrite + Teams license + admin consent.
            meeting_body: dict[str, Any] = {
                "subject": subject,
                "startDateTime": start_dt_z,
                "endDateTime":   end_dt_z,
            }


            async with httpx.AsyncClient() as client:
                resp2 = await client.post(
                    f"{GRAPH_BASE}/me/onlineMeetings",
                    json=meeting_body,
                    headers=headers,
                )

            if resp2.is_success:
                data2 = resp2.json()
                join_url = data2.get("joinWebUrl", "")
                meeting_id = data2.get("id", "")

                # Also send calendar invites to attendees if provided
                if attendees:
                    invite_body: dict[str, Any] = {
                        "subject": subject,
                        "start": {"dateTime": start_dt_plain, "timeZone": "UTC"},
                        "end":   {"dateTime": end_dt_plain,   "timeZone": "UTC"},
                        "isOnlineMeeting": True,
                        "onlineMeetingProvider": "teamsForBusiness",
                        "onlineMeeting": {"joinUrl": join_url},
                        "attendees": [
                            {"emailAddress": {"address": e}, "type": "required"}
                            for e in attendees
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
                            json=invite_body,
                            headers=headers,
                        )

                return {
                    "success": True,
                    "meeting_id": meeting_id,
                    "join_url": join_url,
                    "attendees_invited": len(attendees),
                    "summary": (
                        f"Teams meeting '{subject}' created. "
                        f"Join URL: {join_url}. "
                        f"{len(attendees)} attendee(s) invited via calendar."
                    ),
                }

            # Both strategies failed — report both errors
            try:
                err2 = resp2.json().get("error", {})
                s2_detail = f"{err2.get('code', '')}: {err2.get('message', resp2.text)}"
            except Exception:
                s2_detail = resp2.text

            raise ToolExecutionError(
                "teams_create_meeting",
                (
                    f"Both meeting creation strategies failed.\n"
                    f"  [Calendar /me/events]        {resp.status_code}: {s1_detail}\n"
                    f"  [/me/onlineMeetings fallback] {resp2.status_code}: {s2_detail}"
                ),
            )

        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError("teams_create_meeting", str(exc))


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
                    # 1-on-1 DM — Graph API requires BOTH members (self + recipient)
                    # Step 1: Get the current user's ID
                    me_resp = await client.get(f"{GRAPH_BASE}/me", headers=headers)
                    me_resp.raise_for_status()
                    my_id = me_resp.json()["id"]

                    # Step 2: Create the chat with both members
                    chat_resp = await client.post(
                        f"{GRAPH_BASE}/chats",
                        json={
                            "chatType": "oneOnOne",
                            "members": [
                                {
                                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                                    "roles": ["owner"],
                                    "user@odata.bind": f"{GRAPH_BASE}/users/{my_id}",
                                },
                                {
                                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                                    "roles": ["owner"],
                                    "user@odata.bind": f"{GRAPH_BASE}/users/{recipient_email}",
                                },
                            ],
                        },
                        headers=headers,
                    )
                    if not chat_resp.is_success:
                        try:
                            err = chat_resp.json().get("error", {})
                            detail = f"{err.get('code', '')}: {err.get('message', chat_resp.text)}"
                        except Exception:
                            detail = chat_resp.text
                        raise ToolExecutionError(
                            "teams_send_message",
                            f"Failed to create chat with {recipient_email}: {detail}. "
                            "Note: Both users must be in the same Microsoft 365 tenant for DMs.",
                        )
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
                "summary": "Teams message sent successfully.",
            }
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError("teams_send_message", str(exc))


class ReadTeamsMessagesTool(BaseTool):
    """Read recent messages from a Teams 1-on-1 chat or all recent chats."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="teams_read_messages",
            description=(
                "Read recent messages from Microsoft Teams. "
                "Optionally filter by a specific person's email to read your DM conversation with them. "
                "If no email is provided, returns recent messages from all your latest chats. "
                "Use this when the user wants to check, view, or read Teams messages or conversations."
            ),
            provider="microsoft",
            requires_confirmation=False,
            parameters={
                "type": "object",
                "properties": {
                    "recipient_email": {
                        "type": "string",
                        "description": (
                            "Email of the person whose DM conversation you want to read. "
                            "Leave empty to get messages from your most recent chats."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of messages to return per chat (default: 10, max: 50)",
                    },
                },
                "required": [],
            },
        )

    async def execute(
        self, arguments: dict[str, Any], user_id: str, access_token: str
    ) -> dict[str, Any]:
        recipient_email: str | None = arguments.get("recipient_email")
        limit: int = min(int(arguments.get("limit", 10)), 50)

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:

                # ── Step 1: Fetch all chats with their members expanded ────────
                chats_resp = await client.get(
                    f"{GRAPH_BASE}/me/chats",
                    params={
                        "$expand": "members",
                        "$top": "20",
                        "$orderby": "lastMessagePreview/createdDateTime desc",
                    },
                    headers=headers,
                )

                if chats_resp.status_code == 401:
                    raise ToolExecutionError(
                        "teams_read_messages",
                        (
                            "Your Microsoft token has expired or is missing permissions. "
                            "Go to Settings & Integrations → Outlook / Teams → Disconnect "
                            "and reconnect your account."
                        ),
                    )

                if not chats_resp.is_success:
                    try:
                        err = chats_resp.json().get("error", {})
                        detail = f"{err.get('code', '')}: {err.get('message', chats_resp.text)}"
                    except Exception:
                        detail = chats_resp.text
                    raise ToolExecutionError("teams_read_messages", f"Failed to fetch chats: {detail}")

                all_chats: list[dict] = chats_resp.json().get("value", [])

                if not all_chats:
                    return {
                        "success": True,
                        "messages": [],
                        "summary": "No Teams chats found.",
                    }

                # ── Step 2: Filter to a specific chat if email is given ────────
                target_chats: list[dict] = []

                if recipient_email:
                    recipient_lower = recipient_email.lower()
                    for chat in all_chats:
                        members: list[dict] = chat.get("members", [])
                        emails_in_chat = [
                            (m.get("email") or "").lower() for m in members
                        ]
                        if recipient_lower in emails_in_chat:
                            target_chats.append(chat)
                            break  # oneOnOne — only one match expected

                    if not target_chats:
                        return {
                            "success": True,
                            "messages": [],
                            "summary": (
                                f"No chat conversation found with {recipient_email}. "
                                "You may not have messaged this person before."
                            ),
                        }
                else:
                    # Use the most recent chats (up to 5)
                    target_chats = all_chats[:5]

                # ── Step 3: Fetch messages from each target chat ───────────────
                result_conversations: list[dict] = []

                for chat in target_chats:
                    chat_id: str = chat.get("id", "")
                    chat_type: str = chat.get("chatType", "oneOnOne")

                    # Determine a human-readable chat name
                    members: list[dict] = chat.get("members", [])
                    member_names = [
                        m.get("displayName") or m.get("email") or "Unknown"
                        for m in members
                    ]
                    chat_label = ", ".join(member_names) if member_names else chat_id

                    msgs_resp = await client.get(
                        f"{GRAPH_BASE}/chats/{chat_id}/messages",
                        params={
                            "$top": str(limit),
                            "$orderby": "createdDateTime desc",
                        },
                        headers=headers,
                    )

                    if not msgs_resp.is_success:
                        result_conversations.append({
                            "chat": chat_label,
                            "chat_type": chat_type,
                            "error": f"Could not fetch messages ({msgs_resp.status_code})",
                            "messages": [],
                        })
                        continue

                    raw_messages: list[dict] = msgs_resp.json().get("value", [])

                    # Parse into a clean format
                    parsed_messages = []
                    for msg in raw_messages:
                        sender_info = (msg.get("from") or {})
                        sender_user = (sender_info.get("user") or {})
                        sender_name = sender_user.get("displayName", "Unknown")

                        body_content: str = (msg.get("body") or {}).get("content", "")
                        body_text = re.sub(r"<[^>]+>", "", body_content).strip()

                        if not body_text:
                            continue  # skip system/empty messages

                        parsed_messages.append({
                            "sender": sender_name,
                            "message": body_text,
                            "timestamp": msg.get("createdDateTime", ""),
                            "message_id": msg.get("id", ""),
                        })

                    result_conversations.append({
                        "chat": chat_label,
                        "chat_type": chat_type,
                        "messages": parsed_messages,
                    })

                # ── Step 4: Build a readable summary ─────────────────────────
                total_msgs = sum(len(c["messages"]) for c in result_conversations)
                if recipient_email and result_conversations:
                    first = result_conversations[0]
                    msgs_preview = "; ".join(
                        f'{m["sender"]}: "{m["message"][:60]}"'
                        for m in first["messages"][:3]
                    )
                    summary = (
                        f"Found {total_msgs} message(s) in your conversation with "
                        f"{recipient_email}. Recent: {msgs_preview}"
                    )
                else:
                    summary = (
                        f"Fetched {total_msgs} message(s) across "
                        f"{len(result_conversations)} recent chat(s)."
                    )

                return {
                    "success": True,
                    "conversations": result_conversations,
                    "total_messages": total_msgs,
                    "summary": summary,
                }

        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError("teams_read_messages", str(exc))
