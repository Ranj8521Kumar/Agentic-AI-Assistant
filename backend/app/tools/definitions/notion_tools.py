"""Notion tool definitions and implementations."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from notion_client import AsyncClient

from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError


def _extract_page_id(raw_id: str) -> str:
    """Extracts a Notion page ID from a URL or raw string."""
    match = re.search(r'([a-fA-F0-9]{8}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]{4}-?[a-fA-F0-9]{12})', raw_id)
    if match:
        return match.group(1)
    parts = raw_id.split("-")
    if len(parts) > 0 and len(parts[-1]) == 32:
        return parts[-1]
    return raw_id


def _normalize_date_values(props: dict[str, Any]) -> dict[str, Any]:
    """Convert relative date strings to ISO-8601 dates for Notion."""
    today = date.today()
    _RELATIVE: dict[str, date] = {
        "today":     today,
        "tomorrow":  today + timedelta(days=1),
        "yesterday": today - timedelta(days=1),
        "next week": today + timedelta(weeks=1),
        "next month": date(today.year + (today.month // 12), (today.month % 12) + 1, 1),
    }
    # Also handle "next <weekday>"
    _WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    normalized: dict[str, Any] = {}
    for key, value in props.items():
        if isinstance(value, str):
            low = value.strip().lower()
            if low in _RELATIVE:
                normalized[key] = _RELATIVE[low].isoformat()
                continue
            # "next monday", "next tuesday", etc.
            for i, day_name in enumerate(_WEEKDAYS):
                if low == f"next {day_name}":
                    days_ahead = (i - today.weekday() + 7) % 7 or 7
                    normalized[key] = (today + timedelta(days=days_ahead)).isoformat()
                    break
            else:
                normalized[key] = value
        else:
            normalized[key] = value
    return normalized


class ReadNotionPageTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notion_read_page",
            description=(
                "Read content from a single Notion PAGE (not a database). "
                "Use this ONLY when the user asks to read the text content of a specific page. "
                "Do NOT use this on a database ID — to search/filter rows in a database use notion_query_database. "
                "Pass the page_id from notion_search_pages results (only use IDs with object type 'page')."
            ),
            provider="notion",
            requires_confirmation=False,
            parameters={
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Notion page ID or URL (page type only, not database)"},
                },
                "required": ["page_id"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        page_id = _extract_page_id(arguments["page_id"])
        try:
            client = AsyncClient(auth=access_token)
            page = await client.pages.retrieve(page_id=page_id)
            blocks = await client.blocks.children.list(block_id=page_id)
            content_parts = []
            for block in blocks.get("results", []):
                bt = block.get("type", "")
                text_obj = block.get(bt, {}).get("rich_text", [])
                text = " ".join(t.get("plain_text", "") for t in text_obj)
                if text:
                    content_parts.append(text)
            title = ""
            props = page.get("properties", {})
            for prop in props.values():
                if prop.get("type") == "title":
                    title = " ".join(t.get("plain_text", "") for t in prop.get("title", []))
                    break
            return {"success": True, "title": title, "content": "\n".join(content_parts)}
        except Exception as e:
            raise ToolExecutionError("notion_read_page", str(e))



class AppendNotionPageTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notion_append_page",
            description=(
                "Append content to a Notion page. Supports rich markdown formatting — "
                "use markdown syntax and the tool will convert it to proper Notion blocks:\n"
                "- Headings: # H1, ## H2, ### H3\n"
                "- Checkboxes (to-do): - [ ] unchecked item, - [x] checked item\n"
                "- Bullet list: - item or * item\n"
                "- Numbered list: 1. item\n"
                "- Plain text: any other line becomes a paragraph\n"
                "Pass the full markdown content as the 'content' argument."
            ),
            provider="notion",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Notion page ID"},
                    "content": {
                        "type": "string",
                        "description": (
                            "Markdown-formatted content to append. Supports headings (#, ##, ###), "
                            "checkboxes (- [ ] item, - [x] item), bullets (- item), "
                            "numbered lists (1. item), and plain paragraphs."
                        ),
                    },
                },
                "required": ["page_id", "content"],
            },
        )

    @staticmethod
    def _parse_inline(text: str) -> list[dict]:
        """Parse inline markdown (**bold**, *italic*, `code`, ~~strike~~) into Notion rich_text runs."""
        import re
        # Pattern: captures bold, italic, code, strikethrough, or plain text chunks
        pattern = re.compile(
            r'(\*\*\*(.+?)\*\*\*)'       # bold+italic
            r'|(\*\*(.+?)\*\*)'           # bold
            r'|(\*(.+?)\*)'               # italic
            r'|(`(.+?)`)'                 # inline code
            r'|(~~(.+?)~~)'               # strikethrough
            r'|([^*`~]+|[*`~])',          # plain text (catch-all)
            re.DOTALL
        )
        runs = []
        for m in pattern.finditer(text):
            if m.group(1):   # bold+italic
                runs.append({"type": "text", "text": {"content": m.group(2)},
                             "annotations": {"bold": True, "italic": True}})
            elif m.group(3): # bold
                runs.append({"type": "text", "text": {"content": m.group(4)},
                             "annotations": {"bold": True}})
            elif m.group(5): # italic
                runs.append({"type": "text", "text": {"content": m.group(6)},
                             "annotations": {"italic": True}})
            elif m.group(7): # code
                runs.append({"type": "text", "text": {"content": m.group(8)},
                             "annotations": {"code": True}})
            elif m.group(9): # strikethrough
                runs.append({"type": "text", "text": {"content": m.group(10)},
                             "annotations": {"strikethrough": True}})
            else:             # plain
                chunk = m.group(0)
                if chunk:
                    runs.append({"type": "text", "text": {"content": chunk}})
        return runs if runs else [{"type": "text", "text": {"content": text}}]

    @staticmethod
    def _is_table_row(line: str) -> bool:
        s = line.strip()
        return s.startswith("|") and s.endswith("|") and "|" in s[1:-1]

    @staticmethod
    def _is_separator_row(line: str) -> bool:
        import re
        return bool(re.match(r'^\|[\s\-:|]+\|$', line.strip()))

    @classmethod
    def _parse_table_row(cls, line: str) -> list[str]:
        """Extract cell text from a markdown table row."""
        cells = line.strip().strip("|").split("|")
        return [c.strip() for c in cells]

    @classmethod
    def _markdown_to_blocks(cls, content: str) -> list[dict]:
        """Convert markdown text into a list of Notion block objects."""
        lines = content.splitlines()
        blocks = []
        i = 0

        while i < len(lines):
            raw_line = lines[i]
            line = raw_line.rstrip()

            # ── Empty line → spacer paragraph ────────────────────────────────
            if not line.strip():
                blocks.append({"object": "block", "type": "paragraph",
                               "paragraph": {"rich_text": []}})
                i += 1
                continue

            ri = cls._parse_inline  # shorthand

            # ── Horizontal rule ───────────────────────────────────────────────
            if line.strip() in ("---", "***", "___") or line.strip().replace("-", "") == "":
                if len(line.strip()) >= 3 and all(c in "-*_ " for c in line.strip()):
                    blocks.append({"object": "block", "type": "divider", "divider": {}})
                    i += 1
                    continue

            # ── Markdown table (detect by looking ahead for separator row) ────
            if cls._is_table_row(line) and i + 1 < len(lines) and cls._is_separator_row(lines[i + 1]):
                headers = cls._parse_table_row(line)
                table_width = len(headers)
                rows: list[list[list[dict]]] = []

                # Header row
                rows.append([[{"type": "text", "text": {"content": h}}] for h in headers])

                # Skip separator row
                i += 2

                # Data rows
                while i < len(lines) and cls._is_table_row(lines[i]):
                    cells = cls._parse_table_row(lines[i])
                    # Pad or truncate to match table_width
                    while len(cells) < table_width:
                        cells.append("")
                    cells = cells[:table_width]
                    rows.append([ri(c) for c in cells])
                    i += 1

                blocks.append({
                    "object": "block",
                    "type": "table",
                    "table": {
                        "table_width": table_width,
                        "has_column_header": True,
                        "has_row_header": False,
                    },
                    "children": [
                        {"object": "block", "type": "table_row",
                         "table_row": {"cells": row_cells}}
                        for row_cells in rows
                    ],
                })
                continue

            # ── Headings ──────────────────────────────────────────────────────
            if line.startswith("### "):
                blocks.append({"object": "block", "type": "heading_3",
                               "heading_3": {"rich_text": ri(line[4:].strip())}})
            elif line.startswith("## "):
                blocks.append({"object": "block", "type": "heading_2",
                               "heading_2": {"rich_text": ri(line[3:].strip())}})
            elif line.startswith("# "):
                blocks.append({"object": "block", "type": "heading_1",
                               "heading_1": {"rich_text": ri(line[2:].strip())}})

            # ── Unchecked to-do: - [ ] ────────────────────────────────────────
            elif line.lstrip().startswith("- [ ] ") or line.lstrip() == "- [ ]":
                text = line.lstrip()[6:].strip()
                blocks.append({"object": "block", "type": "to_do",
                               "to_do": {"rich_text": ri(text), "checked": False}})

            # ── Checked to-do: - [x] ─────────────────────────────────────────
            elif line.lstrip().lower().startswith("- [x] ") or line.lstrip().lower() == "- [x]":
                text = line.lstrip()[6:].strip()
                blocks.append({"object": "block", "type": "to_do",
                               "to_do": {"rich_text": ri(text), "checked": True}})

            # ── Bulleted list ─────────────────────────────────────────────────
            elif line.lstrip().startswith("- ") or line.lstrip().startswith("* "):
                text = line.lstrip()[2:].strip()
                blocks.append({"object": "block", "type": "bulleted_list_item",
                               "bulleted_list_item": {"rich_text": ri(text)}})

            # ── Numbered list ─────────────────────────────────────────────────
            elif len(line.lstrip()) > 2 and line.lstrip()[0].isdigit() and ". " in line.lstrip()[:4]:
                dot_idx = line.lstrip().index(". ")
                text = line.lstrip()[dot_idx + 2:].strip()
                blocks.append({"object": "block", "type": "numbered_list_item",
                               "numbered_list_item": {"rich_text": ri(text)}})

            # ── Plain paragraph ───────────────────────────────────────────────
            else:
                blocks.append({"object": "block", "type": "paragraph",
                               "paragraph": {"rich_text": ri(line.strip())}})

            i += 1

        return blocks

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        page_id = _extract_page_id(arguments["page_id"])
        content = arguments["content"]
        try:
            blocks = self._markdown_to_blocks(content)
            client = AsyncClient(auth=access_token)
            # Notion API accepts max 100 blocks per request — chunk if needed
            for i in range(0, len(blocks), 100):
                await client.blocks.children.append(
                    block_id=page_id,
                    children=blocks[i:i + 100],
                )
            return {
                "success": True,
                "blocks_added": len(blocks),
                "summary": f"Appended {len(blocks)} block(s) to Notion page {page_id}.",
            }
        except Exception as e:
            raise ToolExecutionError("notion_append_page", str(e))



class SearchNotionPageTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notion_search_pages",
            description="Search for Notion pages by title or keyword.",
            provider="notion",
            requires_confirmation=False,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"},
                },
                "required": ["query"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        query = arguments.get("query", "")
        try:
            client = AsyncClient(auth=access_token)
            # Search without a filter so both pages AND databases are returned
            results = await client.search(query=query)
            items = []
            for obj in results.get("results", []):
                obj_type = obj.get("object", "")  # "page" or "database"
                title = "Untitled"

                if obj_type == "database":
                    # Database titles live in the top-level "title" array
                    title_arr = obj.get("title", [])
                    title = " ".join(t.get("plain_text", "") for t in title_arr) or "Untitled"
                else:
                    # Page titles live inside a title-type property
                    for prop in obj.get("properties", {}).values():
                        if prop.get("type") == "title":
                            title = " ".join(t.get("plain_text", "") for t in prop.get("title", []))
                            break

                items.append({
                    "id":   obj.get("id"),
                    "type": obj_type,
                    "title": title,
                    "url":  obj.get("url"),
                })
            return {"success": True, "results": items}
        except Exception as e:
            raise ToolExecutionError("notion_search_pages", str(e))


class CreateNotionPageTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notion_create_page",
            description=(
                "Create a new Notion page. "
                "If the user wants a top-level page in their workspace root, omit parent_page_id. "
                "If the user specifies a parent page by name, use notion_search_pages first to get the ID."
            ),
            provider="notion",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "parent_page_id": {
                        "type": "string",
                        "description": (
                            "The ID (UUID) of the parent page. "
                            "Omit entirely to create a top-level page at the workspace root. "
                            "Do NOT pass a name or the string 'workspace_id' — use a real UUID or leave blank."
                        )
                    },
                    "title": {"type": "string", "description": "The title of the new page"},
                    "content": {"type": "string", "description": "The initial content of the new page"},
                },
                "required": ["title", "content"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        raw_parent = arguments.get("parent_page_id", "").strip()
        title = arguments["title"]
        content = arguments["content"]
        try:
            client = AsyncClient(auth=access_token)

            # Build parent: workspace root if no valid page_id was given
            if raw_parent and raw_parent.lower() not in ("workspace_id", "workspace", ""):
                page_id = _extract_page_id(raw_parent)
                parent = {"type": "page_id", "page_id": page_id}
            else:
                parent = {"type": "workspace", "workspace": True}

            new_page = await client.pages.create(
                parent=parent,
                properties={
                    "title": {
                        "title": [{"type": "text", "text": {"content": title}}]
                    }
                },
                children=[
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": content}}]
                        }
                    }
                ]
            )
            return {
                "success": True,
                "page_id": new_page.get("id"),
                "url": new_page.get("url"),
                "summary": f"Created new Notion page '{title}' at {'workspace root' if parent['type'] == 'workspace' else 'specified parent'}."
            }
        except Exception as e:
            raise ToolExecutionError("notion_create_page", str(e))


class ArchiveNotionPageTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notion_archive_page",
            description="Archive (delete) a Notion page or database item.",
            provider="notion",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "The ID of the page to archive/delete"},
                },
                "required": ["page_id"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        page_id = _extract_page_id(arguments["page_id"])
        try:
            client = AsyncClient(auth=access_token)
            await client.pages.update(
                page_id=page_id,
                archived=True
            )
            return {
                "success": True,
                "summary": f"Successfully archived (deleted) Notion page {page_id}."
            }
        except Exception as e:
            raise ToolExecutionError("notion_archive_page", str(e))


class CreateNotionDatabaseTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notion_create_database",
            description="Create a new Notion database. Requires a parent page ID.",
            provider="notion",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "parent_page_id": {
                        "type": "string", 
                        "description": "The ID of the parent page (must be a valid UUID). If the user provides a name, use notion_search_pages first."
                    },
                    "title": {"type": "string", "description": "The title of the database"},
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A list of column names for the database"
                    },
                },
                "required": ["parent_page_id", "title", "columns"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        import httpx

        parent_page_id = _extract_page_id(arguments["parent_page_id"])
        title = arguments["title"]
        columns = arguments["columns"]

        # Build properties — Notion title column must be keyed "Name"
        properties: dict[str, Any] = {"Name": {"title": {}}}

        for col in columns:
            lower_col = col.lower()
            if lower_col in ("name", "task name"):
                continue
            elif "status" in lower_col:
                properties[col] = {
                    "select": {
                        "options": [
                            {"name": "To Do",       "color": "gray"},
                            {"name": "In Progress", "color": "blue"},
                            {"name": "Done",        "color": "green"},
                        ]
                    }
                }
            elif "priority" in lower_col:
                properties[col] = {
                    "select": {
                        "options": [
                            {"name": "High",   "color": "red"},
                            {"name": "Medium", "color": "yellow"},
                            {"name": "Low",    "color": "green"},
                        ]
                    }
                }
            elif "date" in lower_col:
                properties[col] = {"date": {}}
            elif "checkbox" in lower_col or "done" in lower_col:
                properties[col] = {"checkbox": {}}
            elif "number" in lower_col or "count" in lower_col:
                properties[col] = {"number": {}}
            elif "url" in lower_col or "link" in lower_col:
                properties[col] = {"url": {}}
            elif "email" in lower_col:
                properties[col] = {"email": {}}
            elif "phone" in lower_col:
                properties[col] = {"phone_number": {}}
            else:
                properties[col] = {"rich_text": {}}

        payload = {
            "parent":     {"type": "page_id", "page_id": parent_page_id},
            "title":      [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }

        headers = {
            "Authorization":  f"Bearer {access_token}",
            "Content-Type":   "application/json",
            # Pin to stable API version that fully supports properties
            "Notion-Version": "2022-06-28",
        }

        try:
            async with httpx.AsyncClient(timeout=30) as http:
                resp = await http.post(
                    "https://api.notion.com/v1/databases",
                    json=payload,
                    headers=headers,
                )
            data = resp.json()
            if resp.status_code not in (200, 201):
                raise ToolExecutionError(
                    "notion_create_database",
                    data.get("message", str(data))
                )
            created_cols = list(data.get("properties", properties).keys())
            return {
                "success":     True,
                "database_id": data.get("id"),
                "url":         data.get("url"),
                "summary":     f"Created Notion database '{title}' with columns: {', '.join(created_cols)}.",
            }
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("notion_create_database", str(e))


class AddNotionDatabaseRowTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notion_add_database_row",
            description=(
                "Add a new row/task/item to an existing Notion database. "
                "Use this when the user wants to add a task, entry, or record to a Notion database. "
                "Do NOT use notion_create_database for this — use this tool instead. "
                "Always pass both database_id (from notion_search_pages) AND database_name so the "
                "tool can self-correct if the ID is wrong. "
                "IMPORTANT: You MUST populate the 'properties' field with ALL column values the user specified. "
                "For example, if the user says Status=In Progress, Priority=High, Due Date=tomorrow, you MUST "
                "pass: properties={\"Status\": \"In Progress\", \"Priority\": \"High\", \"Due Date\": \"tomorrow\"}. "
                "Relative dates like 'tomorrow', 'today', 'next week' are accepted and will be converted automatically. "
                "Never leave properties empty if the user specified column values."
            ),
            provider="notion",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "database_id": {
                        "type": "string",
                        "description": "The ID (UUID) of the Notion database returned by notion_search_pages.",
                    },
                    "database_name": {
                        "type": "string",
                        "description": (
                            "The human-readable name of the database (e.g. 'Project Tasks'). "
                            "Used as a fallback to re-look-up the correct ID if the provided "
                            "database_id is stale or incorrect."
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "The name/title of the new row (e.g. task name).",
                    },
                    "properties": {
                        "type": "object",
                        "description": (
                            "Key-value pairs for additional columns. "
                            "For select columns (Status, Priority) use: {\"Status\": \"In Progress\"}. "
                            "For date columns use ISO format: {\"Due Date\": \"2026-05-16\"}. "
                            "For text columns use: {\"Notes\": \"some text\"}."
                        ),
                    },
                },
                "required": ["database_id", "name"],
            },
        )

    async def _resolve_database_id(
        self, database_id: str, database_name: str | None, headers: dict, http: Any
    ) -> tuple[str, dict]:
        """Validate the database_id; fall back to name-search if 404. Returns (resolved_id, schema_properties)."""
        resp = await http.get(f"https://api.notion.com/v1/databases/{database_id}", headers=headers)
        if resp.status_code == 200:
            return database_id, resp.json().get("properties", {})

        if resp.status_code == 404 and database_name:
            # LLM may have corrupted the UUID — re-resolve by name
            search_resp = await http.post(
                "https://api.notion.com/v1/search",
                json={"query": database_name, "filter": {"value": "database", "property": "object"}},
                headers=headers,
            )
            for obj in search_resp.json().get("results", []):
                title_text = " ".join(t.get("plain_text", "") for t in obj.get("title", []))
                if database_name.lower() in title_text.lower():
                    resolved_id = obj["id"]
                    # Fetch schema for the resolved database
                    schema_resp = await http.get(
                        f"https://api.notion.com/v1/databases/{resolved_id}",
                        headers=headers,
                    )
                    if schema_resp.status_code == 200:
                        return resolved_id, schema_resp.json().get("properties", {})

        # Could not resolve — surface a clear error
        err_body = resp.json()
        raise ToolExecutionError(
            "notion_add_database_row",
            err_body.get(
                "message",
                f"Could not access database '{database_id}'. "
                "Make sure the database is shared with the 'Agentic AI' integration in Notion.",
            ),
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        import httpx

        raw_database_id = _extract_page_id(arguments["database_id"])
        database_name: str | None = arguments.get("database_name")
        name = arguments["name"]
        extra_props: dict[str, Any] = arguments.get("properties", {}) or {}

        # Normalize relative date strings to ISO format
        extra_props = _normalize_date_values(extra_props)

        headers = {
            "Authorization":  f"Bearer {access_token}",
            "Content-Type":   "application/json",
            "Notion-Version": "2022-06-28",
        }

        try:
            async with httpx.AsyncClient(timeout=30) as http:
                # Validate/resolve the ID and grab the schema in one shot
                database_id, schema = await self._resolve_database_id(
                    raw_database_id, database_name, headers, http
                )

                # Build the properties payload for the new page
                page_props: dict[str, Any] = {}

                # Set the title/name column
                for col_name, col_def in schema.items():
                    if col_def.get("type") == "title":
                        page_props[col_name] = {
                            "title": [{"type": "text", "text": {"content": name}}]
                        }
                        break

                # Map user-supplied values to the correct Notion property format
                for col_name, value in extra_props.items():
                    col_def = schema.get(col_name, {})
                    col_type = col_def.get("type", "rich_text")

                    if col_type in ("select", "status"):
                        page_props[col_name] = {"select": {"name": str(value)}}
                    elif col_type == "multi_select":
                        options = value if isinstance(value, list) else [value]
                        page_props[col_name] = {"multi_select": [{"name": str(o)} for o in options]}
                    elif col_type == "date":
                        page_props[col_name] = {"date": {"start": str(value)}}
                    elif col_type == "checkbox":
                        page_props[col_name] = {"checkbox": bool(value)}
                    elif col_type == "number":
                        page_props[col_name] = {"number": float(value)}
                    elif col_type == "url":
                        page_props[col_name] = {"url": str(value)}
                    elif col_type == "email":
                        page_props[col_name] = {"email": str(value)}
                    elif col_type == "phone_number":
                        page_props[col_name] = {"phone_number": str(value)}
                    else:
                        page_props[col_name] = {
                            "rich_text": [{"type": "text", "text": {"content": str(value)}}]
                        }

                payload = {
                    "parent":     {"type": "database_id", "database_id": database_id},
                    "properties": page_props,
                }

                resp = await http.post(
                    "https://api.notion.com/v1/pages",
                    json=payload,
                    headers=headers,
                )
            data = resp.json()
            if resp.status_code not in (200, 201):
                raise ToolExecutionError("notion_add_database_row", data.get("message", str(data)))

            return {
                "success": True,
                "page_id": data.get("id"),
                "url":     data.get("url"),
                "summary": f"Added '{name}' to the Notion database.",
            }
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("notion_add_database_row", str(e))


class UpdateNotionDatabaseRowTool(BaseTool):
    """Update properties (columns) of an existing row/page inside a Notion database."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notion_update_database_row",
            description=(
                "Update one or more column values of an EXISTING row/task in a Notion database. "
                "Use this when the user wants to change the Status, Priority, Due Date, or any "
                "other column of an existing task (e.g. 'mark Finish AI integration as Done'). "
                "Do NOT use notion_append_page for this — that only adds text to the page body. "
                "Steps: "
                "1. Call notion_search_pages to get the database_id and database_name. "
                "2. Call this tool with database_id, database_name, the row_name (task title to find), "
                "   and properties (the columns to update). "
                "Relative dates ('today', 'tomorrow', 'next week') are accepted and auto-converted."
            ),
            provider="notion",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "database_id": {
                        "type": "string",
                        "description": "The ID (UUID) of the Notion database containing the row.",
                    },
                    "database_name": {
                        "type": "string",
                        "description": "Human-readable database name, used as fallback if database_id is wrong.",
                    },
                    "row_name": {
                        "type": "string",
                        "description": "The exact (or partial) title of the row/task to update (e.g. 'Finish AI integration').",
                    },
                    "properties": {
                        "type": "object",
                        "description": (
                            "Key-value pairs of columns to update. "
                            "For select columns: {\"Status\": \"Done\"}. "
                            "For date columns: {\"Due Date\": \"2026-05-20\"}. "
                            "For text columns: {\"Notes\": \"updated text\"}."
                        ),
                    },
                },
                "required": ["database_id", "row_name", "properties"],
            },
        )

    async def _resolve_database(
        self, database_id: str, database_name: str | None, headers: dict, http: Any
    ) -> tuple[str, dict]:
        """Resolve database_id → (id, schema). Falls back to name search on 404."""
        resp = await http.get(f"https://api.notion.com/v1/databases/{database_id}", headers=headers)
        if resp.status_code == 200:
            return database_id, resp.json().get("properties", {})

        if resp.status_code == 404 and database_name:
            search_resp = await http.post(
                "https://api.notion.com/v1/search",
                json={"query": database_name, "filter": {"value": "database", "property": "object"}},
                headers=headers,
            )
            for obj in search_resp.json().get("results", []):
                title_text = " ".join(t.get("plain_text", "") for t in obj.get("title", []))
                if database_name.lower() in title_text.lower():
                    resolved_id = obj["id"]
                    schema_resp = await http.get(
                        f"https://api.notion.com/v1/databases/{resolved_id}", headers=headers
                    )
                    if schema_resp.status_code == 200:
                        return resolved_id, schema_resp.json().get("properties", {})

        err = resp.json()
        raise ToolExecutionError(
            "notion_update_database_row",
            err.get("message", f"Could not access database '{database_id}'."),
        )

    async def _find_page_in_database(
        self, database_id: str, row_name: str, headers: dict, http: Any
    ) -> tuple[str, str]:
        """Search a database for a page whose title matches row_name. Returns (page_id, page_url)."""
        resp = await http.post(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            json={},
            headers=headers,
        )
        if resp.status_code != 200:
            err = resp.json()
            raise ToolExecutionError(
                "notion_update_database_row",
                err.get("message", "Failed to query database pages."),
            )

        pages = resp.json().get("results", [])
        row_name_lower = row_name.strip().lower()
        best_page_id: str | None = None
        best_page_url: str | None = None

        for page in pages:
            props = page.get("properties", {})
            for prop_def in props.values():
                if prop_def.get("type") == "title":
                    title = " ".join(t.get("plain_text", "") for t in prop_def.get("title", []))
                    if row_name_lower in title.lower():
                        best_page_id = page["id"]
                        best_page_url = page.get("url", "")
                        break
            if best_page_id:
                break

        if not best_page_id:
            raise ToolExecutionError(
                "notion_update_database_row",
                f"Could not find a row named '{row_name}' in the database. "
                "Check the task name and try again.",
            )
        return best_page_id, best_page_url

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        import httpx

        raw_database_id = _extract_page_id(arguments["database_id"])
        database_name: str | None = arguments.get("database_name")
        row_name: str = arguments["row_name"]
        extra_props: dict[str, Any] = arguments.get("properties", {}) or {}
        extra_props = _normalize_date_values(extra_props)

        headers = {
            "Authorization":  f"Bearer {access_token}",
            "Content-Type":   "application/json",
            "Notion-Version": "2022-06-28",
        }

        try:
            async with httpx.AsyncClient(timeout=30) as http:
                # 1. Resolve database id + schema
                database_id, schema = await self._resolve_database(
                    raw_database_id, database_name, headers, http
                )

                # 2. Find the page to update
                page_id, page_url = await self._find_page_in_database(
                    database_id, row_name, headers, http
                )

                # 3. Build the properties update payload
                page_props: dict[str, Any] = {}
                for col_name, value in extra_props.items():
                    col_def = schema.get(col_name, {})
                    col_type = col_def.get("type", "rich_text")

                    if col_type in ("select", "status"):
                        page_props[col_name] = {"select": {"name": str(value)}}
                    elif col_type == "multi_select":
                        options = value if isinstance(value, list) else [value]
                        page_props[col_name] = {"multi_select": [{"name": str(o)} for o in options]}
                    elif col_type == "date":
                        page_props[col_name] = {"date": {"start": str(value)}}
                    elif col_type == "checkbox":
                        page_props[col_name] = {"checkbox": bool(value)}
                    elif col_type == "number":
                        page_props[col_name] = {"number": float(value)}
                    elif col_type == "url":
                        page_props[col_name] = {"url": str(value)}
                    elif col_type == "email":
                        page_props[col_name] = {"email": str(value)}
                    elif col_type == "phone_number":
                        page_props[col_name] = {"phone_number": str(value)}
                    elif col_type == "title":
                        page_props[col_name] = {
                            "title": [{"type": "text", "text": {"content": str(value)}}]
                        }
                    else:
                        page_props[col_name] = {
                            "rich_text": [{"type": "text", "text": {"content": str(value)}}]
                        }

                # 4. PATCH the page properties
                patch_resp = await http.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    json={"properties": page_props},
                    headers=headers,
                )

            data = patch_resp.json()
            if patch_resp.status_code not in (200, 201):
                raise ToolExecutionError(
                    "notion_update_database_row", data.get("message", str(data))
                )

            updated_cols = ", ".join(f"{k}={v}" for k, v in extra_props.items())
            return {
                "success": True,
                "page_id": page_id,
                "url":     page_url,
                "summary": f"Updated '{row_name}' in the Notion database: {updated_cols}.",
            }
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("notion_update_database_row", str(e))


class QueryNotionDatabaseTool(BaseTool):
    """Query/filter rows inside a Notion database."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notion_query_database",
            description=(
                "List, search, or filter rows/tasks inside an existing Notion database. "
                "Use this when the user asks to find, list, or filter tasks by a column value "
                "(e.g. 'find all tasks with status In Progress', 'list all High priority tasks'). "
                "Do NOT use notion_read_page for this — that reads a single page's text body, not database rows. "
                "Steps: "
                "1. Call notion_search_pages to get the database_id and database_name. "
                "2. Call this tool with database_id, database_name, and an optional filter. "
                "Filter format: {\"column\": \"Status\", \"value\": \"In Progress\"} "
                "Leave filter empty to list ALL rows."
            ),
            provider="notion",
            requires_confirmation=False,
            parameters={
                "type": "object",
                "properties": {
                    "database_id": {
                        "type": "string",
                        "description": "The ID (UUID) of the Notion database to query.",
                    },
                    "database_name": {
                        "type": "string",
                        "description": "Human-readable database name, used as fallback if database_id is wrong.",
                    },
                    "filter": {
                        "type": "object",
                        "description": (
                            "Optional filter to apply. Format: {\"column\": \"<column name>\", \"value\": \"<value>\"}. "
                            "Example: {\"column\": \"Status\", \"value\": \"In Progress\"}. "
                            "Omit or pass null to return all rows."
                        ),
                    },
                },
                "required": ["database_id"],
            },
        )

    async def _resolve_database(
        self, database_id: str, database_name: str | None, headers: dict, http: Any
    ) -> tuple[str, dict]:
        """Resolve database_id → (id, schema). Falls back to name search on 404."""
        resp = await http.get(f"https://api.notion.com/v1/databases/{database_id}", headers=headers)
        if resp.status_code == 200:
            return database_id, resp.json().get("properties", {})

        if resp.status_code == 404 and database_name:
            search_resp = await http.post(
                "https://api.notion.com/v1/search",
                json={"query": database_name, "filter": {"value": "database", "property": "object"}},
                headers=headers,
            )
            for obj in search_resp.json().get("results", []):
                title_text = " ".join(t.get("plain_text", "") for t in obj.get("title", []))
                if database_name.lower() in title_text.lower():
                    resolved_id = obj["id"]
                    schema_resp = await http.get(
                        f"https://api.notion.com/v1/databases/{resolved_id}", headers=headers
                    )
                    if schema_resp.status_code == 200:
                        return resolved_id, schema_resp.json().get("properties", {})

        err = resp.json()
        raise ToolExecutionError(
            "notion_query_database",
            err.get("message", f"Could not access database '{database_id}'."),
        )

    def _build_notion_filter(self, col_name: str, value: str, schema: dict) -> dict:
        """Build a Notion API filter object from a column name and value."""
        col_type = schema.get(col_name, {}).get("type", "rich_text")
        if col_type in ("select", "status"):
            return {"property": col_name, "select": {"equals": value}}
        elif col_type == "multi_select":
            return {"property": col_name, "multi_select": {"contains": value}}
        elif col_type == "checkbox":
            return {"property": col_name, "checkbox": {"equals": value.lower() in ("true", "yes", "1")}}
        elif col_type == "date":
            return {"property": col_name, "date": {"equals": value}}
        elif col_type == "number":
            return {"property": col_name, "number": {"equals": float(value)}}
        else:
            return {"property": col_name, "rich_text": {"contains": value}}

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        import httpx

        raw_database_id = _extract_page_id(arguments["database_id"])
        database_name: str | None = arguments.get("database_name")
        filter_arg: dict | None = arguments.get("filter")

        headers = {
            "Authorization":  f"Bearer {access_token}",
            "Content-Type":   "application/json",
            "Notion-Version": "2022-06-28",
        }

        try:
            async with httpx.AsyncClient(timeout=30) as http:
                # Resolve database id + schema (with self-healing UUID fix)
                database_id, schema = await self._resolve_database(
                    raw_database_id, database_name, headers, http
                )

                # Build query payload
                query_payload: dict[str, Any] = {}
                if filter_arg and filter_arg.get("column") and filter_arg.get("value"):
                    col_name = filter_arg["column"]
                    value = str(filter_arg["value"])
                    query_payload["filter"] = self._build_notion_filter(col_name, value, schema)

                resp = await http.post(
                    f"https://api.notion.com/v1/databases/{database_id}/query",
                    json=query_payload,
                    headers=headers,
                )

            if resp.status_code != 200:
                err = resp.json()
                raise ToolExecutionError("notion_query_database", err.get("message", str(err)))

            pages = resp.json().get("results", [])

            # Extract human-readable rows
            rows = []
            for page in pages:
                row: dict[str, Any] = {"id": page["id"], "url": page.get("url", "")}
                for col_name, prop_def in page.get("properties", {}).items():
                    col_type = prop_def.get("type", "")
                    if col_type == "title":
                        row[col_name] = " ".join(t.get("plain_text", "") for t in prop_def.get("title", []))
                    elif col_type in ("select", "status"):
                        sel = prop_def.get("select") or {}
                        row[col_name] = sel.get("name", "")
                    elif col_type == "multi_select":
                        row[col_name] = [o.get("name", "") for o in prop_def.get("multi_select", [])]
                    elif col_type == "date":
                        d = prop_def.get("date") or {}
                        row[col_name] = d.get("start", "")
                    elif col_type == "checkbox":
                        row[col_name] = prop_def.get("checkbox", False)
                    elif col_type == "number":
                        row[col_name] = prop_def.get("number")
                    elif col_type == "rich_text":
                        row[col_name] = " ".join(t.get("plain_text", "") for t in prop_def.get("rich_text", []))
                    elif col_type == "url":
                        row[col_name] = prop_def.get("url", "")
                rows.append(row)

            filter_desc = (
                f" where {filter_arg['column']} = '{filter_arg['value']}'"
                if filter_arg and filter_arg.get("column")
                else ""
            )
            return {
                "success": True,
                "count":   len(rows),
                "rows":    rows,
                "summary": f"Found {len(rows)} row(s) in '{database_name or database_id}'{filter_desc}.",
            }
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError("notion_query_database", str(e))
