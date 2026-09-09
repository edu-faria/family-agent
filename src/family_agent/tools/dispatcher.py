"""Validates, authorizes, gates and audits every tool call the agent makes.

Flow per call:
  1. look up the tool (unknown -> error back to the model, never an exception)
  2. validate input against the pydantic schema
  3. check authz (family / admin)
  4. if tool.writes and not pre-confirmed -> raise ConfirmationRequired (bubbles to
     the conversation manager, which asks the family Yes/No)
  5. run the handler in a transaction-friendly context
  6. audit the outcome
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from family_agent.logging_setup import get_logger
from family_agent.persistence.repositories import AuditRepo
from family_agent.tools.registry import (
    ConfirmationRequired,
    ToolContext,
    ToolError,
    ToolRegistry,
    ToolResult,
)

log = get_logger(__name__)

# Caps so a single tool call can never do bulk damage.
_MAX_ITEMS_PER_CALL = 25


class ToolDispatcher:
    def __init__(self, registry: ToolRegistry, audit: AuditRepo) -> None:
        self.registry = registry
        self.audit = audit

    def call(
        self,
        name: str,
        raw_input: dict[str, Any],
        ctx: ToolContext,
        *,
        pre_confirmed: bool = False,
    ) -> ToolResult:
        tool = self.registry.get(name)
        if tool is None:
            return ToolResult(f"Unknown tool '{name}'.", is_error=True)

        try:
            parsed = tool.input_model.model_validate(raw_input)
        except ValidationError as exc:
            return ToolResult(f"Invalid arguments for {name}: {exc}", is_error=True)

        if tool.authz == "admin" and getattr(ctx, "role", "member") != "admin":
            return ToolResult(f"{name} is admin-only.", is_error=True)

        if _looks_bulk(raw_input):
            return ToolResult(
                f"{name} was asked to touch too many items at once "
                f"(limit {_MAX_ITEMS_PER_CALL}). Split it up.",
                is_error=True,
            )

        if tool.writes and not pre_confirmed:
            summary = tool.summarize(ctx, parsed) if tool.summarize else _default_summary(name, parsed)
            self.audit.record(
                kind="confirm",
                member_id=ctx.member_id,
                chat_id=ctx.chat_id,
                tool_name=name,
                input_obj=raw_input,
                result_summary="proposed",
            )
            raise ConfirmationRequired(name, raw_input, summary)

        try:
            result = tool.handler(ctx, parsed)
        except ToolError as exc:
            self.audit.record(
                kind="tool", member_id=ctx.member_id, chat_id=ctx.chat_id,
                tool_name=name, input_obj=raw_input, result_summary=f"error: {exc}",
            )
            return ToolResult(str(exc), is_error=True)
        except Exception:  # fail closed
            log.exception("tool.crash", tool=name)
            self.audit.record(
                kind="error", member_id=ctx.member_id, chat_id=ctx.chat_id,
                tool_name=name, input_obj=raw_input, result_summary="unhandled exception",
            )
            return ToolResult("Something went wrong running that. Nothing was changed.", is_error=True)

        self.audit.record(
            kind="tool", member_id=ctx.member_id, chat_id=ctx.chat_id,
            tool_name=name, input_obj=raw_input,
            result_summary=(result.content[:280] if not result.is_error else f"error: {result.content[:280]}"),
        )
        return result


def _looks_bulk(raw: dict[str, Any]) -> bool:
    for v in raw.values():
        if isinstance(v, list) and len(v) > _MAX_ITEMS_PER_CALL:
            return True
    return False


def _default_summary(name: str, parsed: Any) -> str:
    fields = getattr(parsed, "model_dump", lambda: {})()
    pretty = ", ".join(f"{k}={v!r}" for k, v in fields.items() if v is not None)
    return f"Run {name} with {pretty}?"
