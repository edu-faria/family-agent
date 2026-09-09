"""The confirmation gate: a writes=True tool must not execute without approval."""

from __future__ import annotations

import pytest

from family_agent.persistence.db import Database
from family_agent.persistence.migrations import run_migrations
from family_agent.persistence.repositories import AuditRepo
from family_agent.tools.dispatcher import ToolDispatcher
from family_agent.tools.registry import (
    ConfirmationRequired,
    Tool,
    ToolContext,
    ToolRegistry,
    ToolResult,
)
from pydantic import BaseModel


class Ping(BaseModel):
    value: str


class _Cap:
    name = "demo"

    def __init__(self):
        self.ran = []

    def tools(self):
        def handler(ctx, data):
            self.ran.append(data.value)
            return ToolResult(f"did {data.value}")

        return [Tool("demo.write", "writes", Ping, handler, writes=True),
                Tool("demo.read", "reads", Ping, handler)]

    def system_prompt_fragment(self):
        return ""

    def scheduled_jobs(self):
        return []


@pytest.fixture
def ctx(tmp_path):
    db = Database(tmp_path / "t.db")
    run_migrations(db, {})
    return db


def _ctx(db):
    return ToolContext(db=db, member_id=1, member_name="x", locale="pt", chat_id=1,
                       timezone="Europe/Berlin", settings=object())


def test_write_tool_requires_confirmation(ctx):
    cap = _Cap()
    reg = ToolRegistry()
    reg.register(cap)
    disp = ToolDispatcher(reg, AuditRepo(ctx))

    with pytest.raises(ConfirmationRequired):
        disp.call("demo.write", {"value": "a"}, _ctx(ctx))
    assert cap.ran == []  # nothing executed

    disp.call("demo.write", {"value": "a"}, _ctx(ctx), pre_confirmed=True)
    assert cap.ran == ["a"]


def test_read_tool_runs_directly(ctx):
    cap = _Cap()
    reg = ToolRegistry()
    reg.register(cap)
    disp = ToolDispatcher(reg, AuditRepo(ctx))
    res = disp.call("demo.read", {"value": "b"}, _ctx(ctx))
    assert res.is_error is False and cap.ran == ["b"]


def test_unknown_tool_is_error_not_exception(ctx):
    reg = ToolRegistry()
    disp = ToolDispatcher(reg, AuditRepo(ctx))
    res = disp.call("nope.nope", {}, _ctx(ctx))
    assert res.is_error is True
