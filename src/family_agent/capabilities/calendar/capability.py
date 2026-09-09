from __future__ import annotations

from pathlib import Path

from family_agent.capabilities.calendar.tools import build_tools
from family_agent.tools.registry import Capability, Tool

_PROMPT = (Path(__file__).parent / "prompt.md").read_text()


class CalendarCapability:
    name = "calendar"

    def tools(self) -> list[Tool]:
        return build_tools()

    def system_prompt_fragment(self) -> str:
        return _PROMPT

    def scheduled_jobs(self) -> list:
        return []  # proactive reminders are a future feature


def get_capability() -> Capability:
    return CalendarCapability()
