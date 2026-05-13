"""Notion tool definitions and implementations."""

from __future__ import annotations

from typing import Any

from notion_client import AsyncClient

from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError


class ReadNotionPageTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notion_read_page",
            description="Read content from a Notion page.",
            provider="notion",
            requires_confirmation=False,
            parameters={
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Notion page ID or URL"},
                },
                "required": ["page_id"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        page_id = arguments["page_id"].split("-")[-1].replace("-", "")
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
            description="Append text content to a Notion page.",
            provider="notion",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Notion page ID"},
                    "content": {"type": "string", "description": "Text to append to the page"},
                },
                "required": ["page_id", "content"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str, **kwargs) -> dict[str, Any]:
        page_id = arguments["page_id"]
        content = arguments["content"]
        try:
            client = AsyncClient(auth=access_token)
            await client.blocks.children.append(
                block_id=page_id,
                children=[
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": content}}]
                        },
                    }
                ],
            )
            return {"success": True, "summary": f"Content appended to Notion page {page_id}."}
        except Exception as e:
            raise ToolExecutionError("notion_append_page", str(e))
