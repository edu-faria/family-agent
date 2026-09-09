"""Render the small Markdown subset the agent emits as Telegram HTML.

HTML parse mode only needs ``< > &`` escaped, so it survives our summaries full of
``.``, ``-``, ``(``, ``#`` — unlike MarkdownV2, which would need all of those
escaped. Unbalanced markers are left as literal text (never a broken tag), so it
is safe to run on a chunk of a longer message.
"""

from __future__ import annotations

import html
import re

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_CODE = re.compile(r"`([^`\n]+)`")
_ITALIC = re.compile(r"(?<![\*_])\*(?!\s)(.+?)(?<!\s)\*(?!\*)", re.DOTALL)


def md_to_telegram_html(text: str) -> str:
    out = html.escape(text, quote=False)
    out = _BOLD.sub(r"<b>\1</b>", out)
    out = _CODE.sub(r"<code>\1</code>", out)
    out = _ITALIC.sub(r"<i>\1</i>", out)
    return out
