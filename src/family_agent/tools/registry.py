"""The contract every capability implements, and the registry that assembles them.

The LLM can ONLY act through `Tool`s registered here. It has no database, shell,
filesystem or network access of its own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from family_agent.persistence.db import Database


@dataclass
class ToolContext:
    """Everything a tool handler is allowed to touch, injected per call."""

    db: Database
    member_id: int
    member_name: str
    locale: str
    chat_id: int
    timezone: str
    settings: Any  # family_agent.config.Settings (avoid import cycle)


ToolHandler = Callable[[ToolContext, BaseModel], "ToolResult"]


@dataclass
class ToolResult:
    """What a handler returns. `content` is fed back to the model as a tool_result."""

    content: str
    data: dict[str, Any] = field(default_factory=dict)
    is_error: bool = False


@dataclass
class Tool:
    name: str                       # namespaced, e.g. "calendar.add_appointment"
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler
    writes: bool = False            # True -> routed through the confirmation gate
    authz: str = "family"          # "family" | "admin"
    # Optional: build the human-readable confirmation summary from validated input.
    summarize: Callable[[ToolContext, BaseModel], str] | None = None

    def json_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }


@runtime_checkable
class Capability(Protocol):
    """A pluggable domain. Drop a package under capabilities/ and list it in config."""

    name: str

    def tools(self) -> list[Tool]: ...
    def system_prompt_fragment(self) -> str: ...
    def scheduled_jobs(self) -> list[Any]: ...  # APScheduler job specs; empty for now


class ToolError(Exception):
    """Raised by a handler for an expected, user-facing failure."""


class ConfirmationRequired(Exception):
    """Raised by the dispatcher when a `writes=True` tool needs a family Yes/No."""

    def __init__(self, tool_name: str, tool_input: dict[str, Any], human_summary: str) -> None:
        super().__init__(human_summary)
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.human_summary = human_summary


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._capabilities: list[Capability] = []

    def register(self, capability: Capability) -> None:
        self._capabilities.append(capability)
        for tool in capability.tools():
            if tool.name in self._tools:
                raise ValueError(f"duplicate tool name: {tool.name}")
            self._tools[tool.name] = tool

    @property
    def capabilities(self) -> list[Capability]:
        return list(self._capabilities)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tools_for(self, capability_names: list[str] | None = None) -> list[Tool]:
        if capability_names is None:
            return list(self._tools.values())
        prefixes = tuple(f"{n}." for n in capability_names)
        return [t for t in self._tools.values() if t.name.startswith(prefixes)]

    def system_prompt(self, capability_names: list[str] | None = None) -> str:
        caps = self._capabilities
        if capability_names is not None:
            caps = [c for c in caps if c.name in capability_names]
        return "\n\n".join(c.system_prompt_fragment().strip() for c in caps if c.system_prompt_fragment())
