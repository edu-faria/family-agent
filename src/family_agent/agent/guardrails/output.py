"""Light pass over the agent's final reply before it goes to Telegram."""

from __future__ import annotations

import re

_LEAK_PATTERNS = [
    re.compile(r"(?i)you are family-agent.*?tool"),   # system-prompt echo
    re.compile(r"sk-[A-Za-z0-9]{20,}"),                # api keys
    re.compile(r"(?i)ANTHROPIC_API_KEY|OPENAI_API_KEY|TELEGRAM_BOT_TOKEN"),
]

TELEGRAM_LIMIT = 4096


def sanitize_output(text: str) -> list[str]:
    """Redact obvious leaks, then split into Telegram-sized chunks."""
    for pat in _LEAK_PATTERNS:
        text = pat.sub("[redacted]", text)
    text = text.strip() or "…"
    return _chunk(text, TELEGRAM_LIMIT)


def _chunk(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks, buf = [], ""
    for line in text.splitlines(keepends=True):
        if len(buf) + len(line) > size:
            chunks.append(buf)
            buf = ""
        buf += line
    if buf:
        chunks.append(buf)
    return chunks
