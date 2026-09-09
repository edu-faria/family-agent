"""The executor: a bounded manual tool-calling loop.

Caps enforced here:
  - at most `max_tool_calls_per_turn` tool calls, then it stops and asks the family
  - a wall-clock deadline per turn
  - the model only sees the tools for the routed capabilities

When a `writes=True` tool is hit, the dispatcher raises ConfirmationRequired; the
loop stops and hands a PendingAction back. The conversation manager persists it and
asks Yes/No. On Yes, `resume_confirmed()` runs that one tool directly (no model)
and lets the model compose the final confirmation line.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from family_agent.agent.providers import Providers, estimate_cost
from family_agent.logging_setup import get_logger
from family_agent.persistence.repositories import AuditRepo
from family_agent.tools.dispatcher import ToolDispatcher
from family_agent.tools.registry import ConfirmationRequired, ToolContext, ToolRegistry
from family_agent.types import (
    OutboundMessage,
    PendingAction,
    TurnResult,
    TurnStatus,
)

log = get_logger(__name__)


class Executor:
    def __init__(
        self,
        providers: Providers,
        registry: ToolRegistry,
        dispatcher: ToolDispatcher,
        audit: AuditRepo,
        settings,
    ) -> None:
        self.providers = providers
        self.registry = registry
        self.dispatcher = dispatcher
        self.audit = audit
        self.settings = settings

    # -- helpers --------------------------------------------------------------
    def _system_prompt(self, ctx: ToolContext, capabilities: list[str]) -> str:
        now = datetime.now(timezone.utc).astimezone()
        base = (
            "You are family-agent, a private assistant for one family. You help with "
            "the family calendar and shopping lists (more domains later). "
            f"Timezone is {ctx.timezone}; resolve all dates/times in it. "
            f"Now is {now:%Y-%m-%d %H:%M %Z}. "
            f"Reply in the user's language; default {self.settings.default_locale}. "
            "Keep German words exactly as written. Be brief and concrete. "
            "You can ONLY act through the provided tools. Never invent appointments, "
            "items, dates or confirmations — if a tool did not return it, you do not "
            "know it. For anything that changes stored data the family will get a "
            "Yes/No prompt automatically; propose the action, don't pretend it's done."
        )
        return base + "\n\n" + self.registry.system_prompt(capabilities)

    def _tool_schemas(self, capabilities: list[str]) -> list[dict]:
        return [t.json_schema() for t in self.registry.tools_for(capabilities)]

    # -- main turn -----------------------------------------------------------
    def run_turn(
        self,
        *,
        ctx: ToolContext,
        capabilities: list[str],
        history: list[dict],
        user_text: str,
    ) -> TurnResult:
        system = self._system_prompt(ctx, capabilities)
        tools = self._tool_schemas(capabilities)
        messages: list[dict] = [*history, {"role": "user", "content": user_text}]

        deadline = time.monotonic() + self.settings.agent.turn_timeout_seconds
        calls_made = 0

        while True:
            if time.monotonic() > deadline:
                return _plain(ctx, "Isso está a demorar demais — tenta reformular, por favor.",
                              TurnStatus.ERROR)

            reply = self.providers.complete(
                model=self.settings.agent.primary_model,
                system=system, messages=messages, tools=tools,
                max_tokens=self.settings.agent.max_output_tokens,
            )
            self.audit.record(
                kind="model", member_id=ctx.member_id, chat_id=ctx.chat_id, model=reply.model,
                result_summary=f"executor stop={reply.stop_reason}",
                input_tokens=reply.input_tokens, output_tokens=reply.output_tokens,
                cost_usd=estimate_cost(reply.model, reply.input_tokens, reply.output_tokens),
            )

            if not reply.wants_tools:
                return _plain(ctx, reply.text or "Feito.", TurnStatus.ANSWERED)

            # Record the assistant turn (with tool_use blocks) verbatim.
            messages.append({"role": "assistant", "content": _assistant_blocks(reply)})

            tool_results = []
            for call in reply.tool_calls:
                calls_made += 1
                if calls_made > self.settings.agent.max_tool_calls_per_turn:
                    return _plain(
                        ctx,
                        "Precisei de muitos passos para isso. Diz-me de forma mais simples o "
                        "que queres e eu tento de novo.",
                        TurnStatus.ERROR,
                    )
                try:
                    result = self.dispatcher.call(call.name, call.arguments, ctx)
                except ConfirmationRequired as cr:
                    action = PendingAction(
                        token=uuid.uuid4().hex[:12],
                        chat_id=ctx.chat_id,
                        member_id=ctx.member_id,
                        tool_name=cr.tool_name,
                        tool_input=cr.tool_input,
                        human_summary=cr.human_summary,
                        created_at=datetime.now(timezone.utc),
                    )
                    return TurnResult(
                        status=TurnStatus.AWAITING_CONFIRMATION,
                        reply=OutboundMessage(
                            chat_id=ctx.chat_id,
                            text=cr.human_summary,
                            buttons=[("✅ Sim", f"confirm:{action.token}"),
                                     ("❌ Não", f"reject:{action.token}")],
                        ),
                        pending_action=action,
                    )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": result.content,
                    "is_error": result.is_error,
                })
            messages.append({"role": "user", "content": tool_results})

    # -- resume after a Yes -------------------------------------------------------
    def resume_confirmed(self, ctx: ToolContext, action: PendingAction) -> TurnResult:
        result = self.dispatcher.call(
            action.tool_name, action.tool_input, ctx, pre_confirmed=True
        )
        if result.is_error:
            return _plain(ctx, f"Não consegui concluir: {result.content}", TurnStatus.ERROR)
        return _plain(ctx, result.content or "Feito.", TurnStatus.ANSWERED)


def _assistant_blocks(reply) -> list[dict]:
    # Prefer the provider's native blocks so thinking blocks are echoed back intact.
    if reply.raw_blocks:
        return reply.raw_blocks
    blocks: list[dict] = []
    if reply.text:
        blocks.append({"type": "text", "text": reply.text})
    for call in reply.tool_calls:
        blocks.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments})
    return blocks


def _plain(ctx: ToolContext, text: str, status: TurnStatus) -> TurnResult:
    return TurnResult(status=status, reply=OutboundMessage(chat_id=ctx.chat_id, text=text))
