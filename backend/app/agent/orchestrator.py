"""
Agent Orchestrator — the main brain of the assistant.
Handles intent recognition, tool selection, confirmation flow, and response aggregation.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.adapter import LLMMessage, LLMResponse
from app.llm.openai_provider import OpenAIProvider
from app.llm.prompt_builder import build_system_prompt
from app.models.message import Message, MessageRole
from app.models.tool_execution import ToolExecution, ToolExecutionStatus
from app.services.auth_service import AuthService
from app.services.google_token_service import refresh_google_token
from app.services.ms_token_service import refresh_microsoft_token
from app.services.token_vault import token_vault
from app.tools.registry import registry


# Sentinel token emitted to the SSE stream to signal tool call status
TOOL_EVENT_PREFIX = "__tool_event__:"


class AgentOrchestrator:
    """
    Core agent brain.
    - Builds conversation context from DB history
    - Calls the LLM with available tools
    - Handles tool calls: confirmation check → token retrieval → execution
    - Streams final answer back to the client in real-time
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.llm = OpenAIProvider()
        self.auth_service = AuthService(db)

    async def run(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        user_message: str,
        history: list[Message],
    ) -> AsyncIterator[str]:
        """
        Main agentic loop. Yields SSE-compatible string chunks.
        The loop continues until the LLM produces a final text response
        (finish_reason == "stop") with no pending tool calls.
        """
        # ── Build context ────────────────────────────────────────────────────
        accounts = await self.auth_service.list_connected_accounts(user_id)
        connected_providers = [a.provider for a in accounts]
        user = await self.auth_service.get_user_by_id(user_id)

        system_prompt = build_system_prompt(
            connected_providers=connected_providers,
            username=user.full_name if user else None,
        )

        # Build message list for LLM
        messages: list[LLMMessage] = [LLMMessage(role="system", content=system_prompt)]
        for msg in history:
            lmsg = LLMMessage(role=msg.role.value, content=msg.content)
            if msg.tool_calls:
                lmsg.tool_calls = msg.tool_calls
            if msg.tool_call_id:
                lmsg.tool_call_id = msg.tool_call_id
            messages.append(lmsg)

        # Append new user message
        messages.append(LLMMessage(role="user", content=user_message))

        # ── Get available tools for connected providers ───────────────────────
        provider_map = {
            "google": ["google"],
            "microsoft": ["microsoft"],
            "slack": ["slack"],
            "jira": ["jira"],
            "notion": ["notion"],
        }
        tool_providers: list[str] = []
        for p in connected_providers:
            tool_providers.extend(provider_map.get(p, []))

        openai_tools = registry.get_openai_functions(providers=tool_providers if tool_providers else None)

        # ── Agentic loop ─────────────────────────────────────────────────────
        max_iterations = 10
        for iteration in range(max_iterations):
            response: LLMResponse = await self.llm.complete(
                messages=messages,
                tools=openai_tools if openai_tools else None,
            )

            # If LLM returned text with no tool calls → yield the final answer in chunks
            if not response.tool_calls:
                final_text = response.content or ""
                # Yield in small chunks so the frontend renders progressively
                async for chunk in self._stream_text(final_text):
                    # JSON-encode the chunk so newlines/special chars survive SSE transport
                    yield json.dumps(chunk)
                return

            # LLM wants to call tools — add assistant message with tool_calls to context
            messages.append(LLMMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            ))

            # Process each tool call
            for tool_call in response.tool_calls:
                tool_name = tool_call["function"]["name"]
                raw_args = tool_call["function"]["arguments"]
                try:
                    arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    arguments = {}

                tool = registry.get(tool_name)
                if tool is None:
                    error_msg = f"Tool '{tool_name}' is not available."
                    messages.append(LLMMessage(
                        role="tool",
                        tool_call_id=tool_call["id"],
                        content=json.dumps({"error": error_msg}),
                        name=tool_name,
                    ))
                    yield f"{TOOL_EVENT_PREFIX}{json.dumps({'tool': tool_name, 'status': 'error', 'message': error_msg})}\n"
                    continue

                # Emit tool-start event
                yield f"{TOOL_EVENT_PREFIX}{json.dumps({'tool': tool_name, 'status': 'running', 'args': arguments})}\n"

                # Check if confirmation is needed
                if tool.definition.requires_confirmation:
                    yield f"{TOOL_EVENT_PREFIX}{json.dumps({'tool': tool_name, 'status': 'awaiting_confirmation'})}\n"

                # ── Get a valid access token (auto-refresh if expired) ─────────
                provider = tool.definition.provider
                account = await self.auth_service.get_connected_account(user_id, provider)
                if account is None or account.encrypted_access_token is None:
                    error_msg = f"No connected account for provider '{provider}'. Please connect it in Settings."
                    messages.append(LLMMessage(
                        role="tool",
                        tool_call_id=tool_call["id"],
                        content=json.dumps({"error": error_msg}),
                        name=tool_name,
                    ))
                    yield f"{TOOL_EVENT_PREFIX}{json.dumps({'tool': tool_name, 'status': 'error', 'message': error_msg})}\n"
                    continue

                # Transparently refresh stale tokens for Google and Microsoft
                if provider == "google":
                    try:
                        access_token = await refresh_google_token(self.auth_service, account)
                    except RuntimeError as refresh_err:
                        error_msg = str(refresh_err)
                        messages.append(LLMMessage(
                            role="tool",
                            tool_call_id=tool_call["id"],
                            content=json.dumps({"error": error_msg}),
                            name=tool_name,
                        ))
                        yield f"{TOOL_EVENT_PREFIX}{json.dumps({'tool': tool_name, 'status': 'error', 'message': error_msg})}\n"
                        continue
                elif provider == "microsoft":
                    try:
                        access_token = await refresh_microsoft_token(self.auth_service, account)
                    except RuntimeError as refresh_err:
                        error_msg = str(refresh_err)
                        messages.append(LLMMessage(
                            role="tool",
                            tool_call_id=tool_call["id"],
                            content=json.dumps({"error": error_msg}),
                            name=tool_name,
                        ))
                        yield f"{TOOL_EVENT_PREFIX}{json.dumps({'tool': tool_name, 'status': 'error', 'message': error_msg})}\n"
                        continue
                else:
                    access_token = token_vault.retrieve(account.encrypted_access_token)

                # Create ToolExecution audit record (started)
                started = datetime.now(timezone.utc)
                tool_exec = ToolExecution(
                    conversation_id=conversation_id,
                    tool_name=tool_name,
                    input_data=arguments,
                    status=ToolExecutionStatus.RUNNING,
                    started_at=started,
                )
                self.db.add(tool_exec)
                await self.db.flush()

                # Execute the tool
                try:
                    # For Microsoft tools, also retrieve Google token (if connected)
                    # so the tool can fall back to Gmail for email delivery.
                    extra_tokens: dict[str, str] | None = None
                    if provider == "microsoft" and "google" in connected_providers:
                        try:
                            google_account = await self.auth_service.get_connected_account(user_id, "google")
                            if google_account and google_account.encrypted_access_token:
                                from app.services.google_token_service import refresh_google_token
                                g_token = await refresh_google_token(self.auth_service, google_account)
                                extra_tokens = {"google": g_token}
                        except Exception:
                            pass  # Gmail fallback is best-effort; don't block the main tool

                    result = await tool.execute(
                        arguments=arguments,
                        user_id=str(user_id),
                        access_token=access_token,
                        extra_tokens=extra_tokens,
                    )
                    finished = datetime.now(timezone.utc)
                    # Update audit record — success
                    tool_exec.status = ToolExecutionStatus.SUCCESS
                    tool_exec.output_data = result
                    tool_exec.finished_at = finished
                    tool_exec.duration_seconds = (finished - started).total_seconds()

                    yield f"{TOOL_EVENT_PREFIX}{json.dumps({'tool': tool_name, 'status': 'success', 'result': result})}\n"
                    messages.append(LLMMessage(
                        role="tool",
                        tool_call_id=tool_call["id"],
                        content=json.dumps(result),
                        name=tool_name,
                    ))
                except Exception as e:
                    finished = datetime.now(timezone.utc)
                    error_msg = str(e)
                    # Update audit record — failure
                    tool_exec.status = ToolExecutionStatus.FAILED
                    tool_exec.error_message = error_msg
                    tool_exec.finished_at = finished
                    tool_exec.duration_seconds = (finished - started).total_seconds()

                    yield f"{TOOL_EVENT_PREFIX}{json.dumps({'tool': tool_name, 'status': 'error', 'message': error_msg})}\n"
                    messages.append(LLMMessage(
                        role="tool",
                        tool_call_id=tool_call["id"],
                        content=json.dumps({"error": error_msg}),
                        name=tool_name,
                    ))

        # Safety valve — if we exit the loop without returning, yield a fallback
        yield json.dumps("I wasn't able to complete the task within the allowed steps. Please try rephrasing your request.")

    async def _stream_text(self, text: str) -> AsyncIterator[str]:
        """Yield the final response text in small chunks (kept for compatibility)."""
        chunk_size = 50
        for i in range(0, len(text), chunk_size):
            yield text[i:i + chunk_size]
