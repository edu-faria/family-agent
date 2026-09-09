from __future__ import annotations

from pathlib import Path

from family_agent.capabilities.shopping.tools import build_tools
from family_agent.tools.registry import Capability, Tool

_PROMPT = (Path(__file__).parent / "prompt.md").read_text()


class ShoppingCapability:
    name = "shopping"

    def tools(self) -> list[Tool]:
        return build_tools()

    def system_prompt_fragment(self) -> str:
        return _PROMPT

    def scheduled_jobs(self) -> list:
        return []


def get_capability() -> Capability:
    return ShoppingCapability()
