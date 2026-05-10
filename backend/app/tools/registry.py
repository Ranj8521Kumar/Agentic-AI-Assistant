"""
Tool Registry — single source of truth for all available tools.
Tools register themselves here; the agent queries this registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.tools.base import BaseTool, ToolDefinition

if TYPE_CHECKING:
    pass


class ToolRegistry:
    """
    Central registry for all agent tools.
    The agent orchestrator reads definitions from here and dispatches executions.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        name = tool.definition.name
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Return a tool by name."""
        return self._tools.get(name)

    def get_definitions(
        self, providers: list[str] | None = None
    ) -> list[ToolDefinition]:
        """
        Return all tool definitions, optionally filtered by provider.
        Used by the agent to know which tools are available.
        """
        tools = self._tools.values()
        if providers is not None:
            tools = [t for t in tools if t.definition.provider in providers]
        return [t.definition for t in tools]

    def get_openai_functions(
        self, providers: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Return tools in OpenAI function-calling format."""
        return [d.to_openai_function() for d in self.get_definitions(providers)]

    def all_tool_names(self) -> list[str]:
        return list(self._tools.keys())


# ── Global registry instance ──────────────────────────────────────────────────

registry = ToolRegistry()


def bootstrap_registry() -> None:
    """Register all built-in tools. Call once at app startup."""
    from app.tools.definitions.gmail_tools import (
        SendEmailTool,
        ReadInboxTool,
        ReadThreadTool,
    )
    from app.tools.definitions.slack_tools import (
        SendSlackMessageTool,
        ReadSlackChannelTool,
    )
    from app.tools.definitions.calendar_tools import (
        ScheduleMeetingTool,
        ListEventsTool,
    )
    from app.tools.definitions.jira_tools import (
        CreateJiraIssueTool,
        UpdateJiraIssueTool,
        SearchJiraIssuesTool,
    )
    from app.tools.definitions.notion_tools import (
        ReadNotionPageTool,
        AppendNotionPageTool,
    )
    from app.tools.definitions.outlook_tools import (
        SendOutlookEmailTool,
        ReadOutlookInboxTool,
    )
    from app.tools.definitions.teams_tools import (
        SendTeamsMessageTool,
        CreateTeamsMeetingTool,
        ReadTeamsMessagesTool,
    )

    for tool in [
        SendEmailTool(),
        ReadInboxTool(),
        ReadThreadTool(),
        SendSlackMessageTool(),
        ReadSlackChannelTool(),
        ScheduleMeetingTool(),
        ListEventsTool(),
        CreateJiraIssueTool(),
        UpdateJiraIssueTool(),
        SearchJiraIssuesTool(),
        ReadNotionPageTool(),
        AppendNotionPageTool(),
        SendOutlookEmailTool(),
        ReadOutlookInboxTool(),
        SendTeamsMessageTool(),
        CreateTeamsMeetingTool(),
        ReadTeamsMessagesTool(),
    ]:
        registry.register(tool)
