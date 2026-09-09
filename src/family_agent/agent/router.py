"""Cheap first-pass classifier.

One small-model call decides: is this in scope, which capability(ies) are relevant,
and is it a plain read that can skip the expensive executor. Keeps the executor's
prompt small (only the relevant tools) and avoids big-model spend on smalltalk.

If the router call fails, we fail open to "all capabilities, use executor".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from family_agent.agent.providers import Providers, estimate_cost
from family_agent.logging_setup import get_logger
from family_agent.persistence.repositories import AuditRepo

log = get_logger(__name__)

_SYSTEM = """You are a router for a family assistant. Reply with ONLY a JSON object:
{{"in_scope": bool, "capabilities": [string], "needs_executor": bool, "reply": string}}

Available capabilities: {capabilities}.
- in_scope: is the user asking about the family's calendar, shopping, or another
  listed capability? Smalltalk/greetings are in_scope with needs_executor=false and
  a short `reply`.
- capabilities: which ones are relevant (subset of the list).
- needs_executor: true if fulfilling this needs tools / multi-step reasoning.
- reply: only when needs_executor is false — a short answer in the user's language
  (default Portuguese; keep any German words as written).
Return nothing but the JSON."""


@dataclass
class RouteDecision:
    in_scope: bool
    capabilities: list[str] = field(default_factory=list)
    needs_executor: bool = True
    direct_reply: str = ""


class Router:
    def __init__(self, providers: Providers, audit: AuditRepo, model: str, capabilities: list[str]) -> None:
        self.providers = providers
        self.audit = audit
        self.model = model
        self.capabilities = capabilities

    def route(self, text: str, history: list[dict], member_id: int, chat_id: int) -> RouteDecision:
        system = _SYSTEM.format(capabilities=", ".join(self.capabilities))
        messages = [*history, {"role": "user", "content": text}]
        try:
            reply = self.providers.complete(
                model=self.model, system=system, messages=messages,
                tools=None, max_tokens=300, force_json=True,
            )
            self.audit.record(
                kind="model", member_id=member_id, chat_id=chat_id, model=reply.model,
                result_summary="router", input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                cost_usd=estimate_cost(reply.model, reply.input_tokens, reply.output_tokens),
            )
            data = json.loads(_extract_json(reply.text))
            caps = [c for c in data.get("capabilities", []) if c in self.capabilities]
            return RouteDecision(
                in_scope=bool(data.get("in_scope", True)),
                capabilities=caps or self.capabilities,
                needs_executor=bool(data.get("needs_executor", True)),
                direct_reply=str(data.get("reply", "")).strip(),
            )
        except Exception as exc:  # fail open
            log.warning("router.failed", error=str(exc))
            return RouteDecision(in_scope=True, capabilities=self.capabilities, needs_executor=True)


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else "{}"
