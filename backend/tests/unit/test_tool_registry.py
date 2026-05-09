"""Unit tests for the tool registry."""

import pytest
from app.tools.registry import ToolRegistry, bootstrap_registry, registry
from app.tools.base import BaseTool, ToolDefinition


class MockTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="mock_tool",
            description="A mock tool for testing",
            provider="mock",
            requires_confirmation=False,
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def execute(self, arguments, user_id, access_token):
        return {"success": True, "data": "mock_result"}


def test_registry_register_and_get():
    reg = ToolRegistry()
    tool = MockTool()
    reg.register(tool)
    assert reg.get("mock_tool") is tool


def test_registry_duplicate_raises():
    reg = ToolRegistry()
    reg.register(MockTool())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(MockTool())


def test_registry_get_definitions_no_filter():
    reg = ToolRegistry()
    reg.register(MockTool())
    defs = reg.get_definitions()
    assert len(defs) == 1
    assert defs[0].name == "mock_tool"


def test_registry_get_definitions_provider_filter():
    reg = ToolRegistry()
    reg.register(MockTool())
    # filter by correct provider
    defs = reg.get_definitions(providers=["mock"])
    assert len(defs) == 1
    # filter by non-existent provider
    defs = reg.get_definitions(providers=["gmail"])
    assert len(defs) == 0


def test_openai_function_format():
    reg = ToolRegistry()
    reg.register(MockTool())
    fns = reg.get_openai_functions()
    assert len(fns) == 1
    fn = fns[0]
    assert fn["type"] == "function"
    assert fn["function"]["name"] == "mock_tool"


def test_bootstrap_registry_registers_all_tools():
    """All expected tool names should be registered after bootstrap."""
    # Use a fresh registry to avoid conflicts
    from app.tools.registry import ToolRegistry
    fresh = ToolRegistry()

    # Temporarily patch
    import app.tools.registry as reg_module
    original = reg_module.registry
    reg_module.registry = fresh
    try:
        bootstrap_registry()
        names = fresh.all_tool_names()
        expected = [
            "gmail_send_email", "gmail_read_inbox", "gmail_read_thread",
            "slack_send_message", "slack_read_channel",
            "calendar_schedule_meeting", "calendar_list_events",
            "jira_create_issue", "jira_update_issue", "jira_search_issues",
            "notion_read_page", "notion_append_page",
            "outlook_send_email", "outlook_read_inbox",
            "teams_send_message",
        ]
        for name in expected:
            assert name in names, f"Tool '{name}' not registered"
    finally:
        reg_module.registry = original
