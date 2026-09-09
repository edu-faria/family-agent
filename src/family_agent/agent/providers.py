"""LLM provider access + routing + fallback.

`complete()` takes a provider-neutral request (system, messages, tools) and returns
a `ModelReply`. Anthropic is the primary; on error/timeout we fall back to OpenAI.
Both are called through their official SDKs.

Pricing table (USD per 1M tokens) is used only for the budget guardrail's cost
estimate; keep it roughly current.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from family_agent.logging_setup import get_logger

log = get_logger(__name__)

# per 1M tokens: (input, output)
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = PRICING.get(model, (0.0, 0.0))
    return input_tokens / 1_000_000 * inp + output_tokens / 1_000_000 * out


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelReply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class Providers:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._anthropic = None
        self._openai = None

    # --- lazy clients ---------------------------------------------------------
    @property
    def anthropic(self):
        if self._anthropic is None:
            import anthropic

            self._anthropic = anthropic.Anthropic(api_key=self.settings.anthropic_api_key or None)
        return self._anthropic

    @property
    def openai(self):
        if self._openai is None:
            from openai import OpenAI

            self._openai = OpenAI(api_key=self.settings.openai_api_key or None)
        return self._openai

    # --- unified entry point ----------------------------------------------------
    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1200,
        force_json: bool = False,
    ) -> ModelReply:
        primary = model
        fallback = self.settings.agent.fallback_model
        try:
            if primary.startswith("claude"):
                return self._anthropic_complete(primary, system, messages, tools, max_tokens, force_json)
            return self._openai_complete(primary, system, messages, tools, max_tokens, force_json)
        except Exception as exc:  # provider outage / timeout / rate limit
            log.warning("provider.primary_failed", model=primary, error=str(exc))
            if fallback and fallback != primary:
                if fallback.startswith("claude"):
                    return self._anthropic_complete(fallback, system, messages, tools, max_tokens, force_json)
                return self._openai_complete(fallback, system, messages, tools, max_tokens, force_json)
            raise

    # --- Anthropic ------------------------------------------------------------
    def _anthropic_complete(self, model, system, messages, tools, max_tokens, force_json) -> ModelReply:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "thinking": {"type": "adaptive"},
        }
        if tools:
            kwargs["tools"] = tools
        resp = self.anthropic.messages.create(**kwargs)
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
        return ModelReply(
            text="".join(text_parts).strip(),
            tool_calls=calls,
            stop_reason=resp.stop_reason or "end_turn",
            model=model,
            input_tokens=getattr(resp.usage, "input_tokens", 0),
            output_tokens=getattr(resp.usage, "output_tokens", 0),
        )

    # --- OpenAI -------------------------------------------------------------------
    def _openai_complete(self, model, system, messages, tools, max_tokens, force_json) -> ModelReply:
        oai_messages = [{"role": "system", "content": system}, *_to_openai_messages(messages)]
        kwargs: dict[str, Any] = {"model": model, "messages": oai_messages, "max_tokens": max_tokens}
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": {
                    "name": t["name"], "description": t["description"],
                    "parameters": t["input_schema"],
                }}
                for t in tools
            ]
        if force_json:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.openai.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        calls: list[ToolCall] = []
        for tc in choice.message.tool_calls or []:
            import json

            calls.append(ToolCall(id=tc.id, name=tc.function.name,
                                  arguments=json.loads(tc.function.arguments or "{}")))
        return ModelReply(
            text=(choice.message.content or "").strip(),
            tool_calls=calls,
            stop_reason="tool_use" if calls else "end_turn",
            model=model,
            input_tokens=getattr(resp.usage, "prompt_tokens", 0),
            output_tokens=getattr(resp.usage, "completion_tokens", 0),
        )


def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten our Anthropic-shaped message list to OpenAI chat format (best effort)."""
    out: list[dict[str, Any]] = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        # list of blocks: keep text, summarize tool_result blocks
        chunks: list[str] = []
        for block in content:
            if block.get("type") == "text":
                chunks.append(block["text"])
            elif block.get("type") == "tool_result":
                chunks.append(f"[tool result] {block.get('content')}")
            elif block.get("type") == "tool_use":
                chunks.append(f"[called {block.get('name')} {block.get('input')}]")
        out.append({"role": m["role"], "content": "\n".join(chunks)})
    return out
