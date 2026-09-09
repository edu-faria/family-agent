"""Regression guards for the provider wire boundary (tool-name pattern, thinking)."""

from __future__ import annotations

from family_agent.agent.providers import (
    _local_name,
    _supports_adaptive_thinking,
    _wire_name,
)

TOOL_NAME_RE = r"^[a-zA-Z0-9_-]{1,128}$"


def test_wire_name_matches_api_pattern():
    import re

    for name in [
        "calendar.add_appointment",
        "calendar.check_car_availability",
        "shopping.mark_bought",
    ]:
        wired = _wire_name(name)
        assert re.match(TOOL_NAME_RE, wired), wired
        assert _local_name(wired) == name  # round-trips


def test_adaptive_thinking_gating():
    assert _supports_adaptive_thinking("claude-opus-5")
    assert _supports_adaptive_thinking("claude-sonnet-5")
    assert not _supports_adaptive_thinking("claude-haiku-4-5")
    assert not _supports_adaptive_thinking("claude-3-5-haiku-latest")
