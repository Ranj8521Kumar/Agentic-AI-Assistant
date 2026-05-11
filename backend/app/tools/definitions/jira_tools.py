"""Jira tool definitions and implementations."""

from __future__ import annotations

from typing import Any

from atlassian import Jira

from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError


def _build_jira(access_token: str) -> Jira:
    """
    Build a Jira client using Atlassian API token basic auth.
    access_token is stored as 'email:api_token' in the database.
    """
    from app.config import settings
    if ":" in access_token:
        email, api_token = access_token.split(":", 1)
    else:
        # Legacy / fallback — treat entire value as token with no email
        email, api_token = "", access_token
    return Jira(
        url=settings.JIRA_BASE_URL,
        username=email,
        password=api_token,
        cloud=True,
    )


class CreateJiraIssueTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="jira_create_issue",
            description="Create a new Jira issue in a project.",
            provider="jira",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string", "description": "Jira project key, e.g. PROJ"},
                    "summary": {"type": "string", "description": "Issue summary"},
                    "description": {"type": "string", "description": "Issue description"},
                    "issue_type": {"type": "string", "default": "Task"},
                    "priority": {"type": "string", "default": "Medium"},
                },
                "required": ["project_key", "summary"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str) -> dict[str, Any]:
        from app.config import settings
        try:
            jira = _build_jira(access_token)
            fields: dict[str, Any] = {
                "project": {"key": arguments["project_key"]},
                "summary": arguments["summary"],
                "description": arguments.get("description", ""),
                "issuetype": {"name": arguments.get("issue_type", "Task")},
                "priority": {"name": arguments.get("priority", "Medium")},
            }
            issue = jira.issue_create(fields=fields)
            key = issue.get("key", "")
            return {"success": True, "issue_key": key, "url": f"{settings.JIRA_BASE_URL}/browse/{key}"}
        except Exception as e:
            raise ToolExecutionError("jira_create_issue", str(e))


class UpdateJiraIssueTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="jira_update_issue",
            description="Update fields on an existing Jira issue.",
            provider="jira",
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Jira issue key"},
                    "summary": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string", "description": "Status to transition to"},
                    "priority": {"type": "string"},
                },
                "required": ["issue_key"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str) -> dict[str, Any]:
        try:
            jira = _build_jira(access_token)
            key = arguments["issue_key"]
            fields: dict[str, Any] = {}
            for field in ("summary", "description"):
                if arguments.get(field):
                    fields[field] = arguments[field]
            if arguments.get("priority"):
                fields["priority"] = {"name": arguments["priority"]}
            if fields:
                jira.update_issue_field(key=key, fields=fields)
            if arguments.get("status"):
                transitions = jira.get_issue_transitions(key)
                # Library returns: [{"name": str, "id": int, "to": str}, ...]
                # "to" is the target status name string; "id" is an int
                target_status = str(arguments["status"]).lower()
                matched = False
                for t in transitions:
                    if str(t["to"]).lower() == target_status:
                        # POST directly with stringified id — bypasses the broken
                        # library helper that calls .lower() on the int id
                        base_url = jira.resource_url("issue")
                        url = f"{base_url}/{key}/transitions"
                        jira.post(url, data={"transition": {"id": str(t["id"])}})
                        matched = True
                        break
                if not matched:
                    available = [str(t["to"]) for t in transitions]
                    raise ValueError(
                        f"Status '{arguments['status']}' is not a valid transition. "
                        f"Available transitions: {', '.join(available)}"
                    )
            return {"success": True, "issue_key": key}
        except Exception as e:
            raise ToolExecutionError("jira_update_issue", str(e))


class SearchJiraIssuesTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="jira_search_issues",
            description="Search Jira issues using JQL.",
            provider="jira",
            requires_confirmation=False,
            parameters={
                "type": "object",
                "properties": {
                    "jql": {"type": "string", "description": "JQL query"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["jql"],
            },
        )

    async def execute(self, arguments: dict[str, Any], user_id: str, access_token: str) -> dict[str, Any]:
        try:
            jira = _build_jira(access_token)
            results = jira.jql(arguments["jql"], limit=min(int(arguments.get("max_results", 10)), 50))
            issues = [
                {
                    "key": i["key"],
                    "summary": i["fields"].get("summary", ""),
                    "status": i["fields"].get("status", {}).get("name", ""),
                }
                for i in results.get("issues", [])
            ]
            return {"success": True, "count": len(issues), "issues": issues}
        except Exception as e:
            raise ToolExecutionError("jira_search_issues", str(e))
