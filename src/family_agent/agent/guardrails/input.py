"""Cheap, deterministic checks on the inbound message before it reaches the agent.

- length cap
- obvious prompt-injection patterns (flagged, not blocked — the agent is told)
- scope pre-filter: hard-decline clearly off-domain requests without spending a
  model call. Ambiguous stuff passes through to the router.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all|any|previous) instructions", re.I),
    re.compile(r"disregard (the )?(system|above)", re.I),
    re.compile(r"you are now (a|an) ", re.I),
    re.compile(r"</?(system|assistant|tool)[ _-]?prompt>", re.I),
    re.compile(r"reveal (your )?(system prompt|instructions)", re.I),
]

# Clearly outside "family calendar + shopping + future household stuff".
_OUT_OF_SCOPE = [
    re.compile(r"\b(write|debug|refactor) (me )?(some )?code\b", re.I),
    re.compile(r"\b(stock|crypto|bitcoin) (price|tips?)\b", re.I),
    re.compile(r"\bmedical (advice|diagnosis)\b", re.I),
    re.compile(r"\b(weather|forecast)\b", re.I),
    re.compile(r"\bnews\b", re.I),
]


class Decision(str, Enum):
    ALLOW = "allow"
    REFUSE_OUT_OF_SCOPE = "refuse_out_of_scope"
    REFUSE_TOO_LONG = "refuse_too_long"


@dataclass
class InputVerdict:
    decision: Decision
    injection_suspected: bool
    note: str = ""


class InputGuard:
    def __init__(self, max_chars: int) -> None:
        self.max_chars = max_chars

    def evaluate(self, text: str) -> InputVerdict:
        if len(text) > self.max_chars:
            return InputVerdict(Decision.REFUSE_TOO_LONG, False,
                                f"message over {self.max_chars} chars")

        injection = any(p.search(text) for p in _INJECTION_PATTERNS)

        if any(p.search(text) for p in _OUT_OF_SCOPE):
            return InputVerdict(Decision.REFUSE_OUT_OF_SCOPE, injection, "matched out-of-scope pattern")

        return InputVerdict(Decision.ALLOW, injection)
