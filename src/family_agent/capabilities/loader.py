"""Discovery of enabled capabilities.

Each capability package under this folder must expose `get_capability() -> Capability`
and keep its migrations in `<pkg>/migrations/*.sql`. To add a domain: create the
package, implement the Capability protocol, and add its name to
`enabled_capabilities` in config.toml. No core code changes.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from family_agent.logging_setup import get_logger
from family_agent.tools.registry import Capability

log = get_logger(__name__)

_PKG = "family_agent.capabilities"


def load_capabilities(names: list[str] | tuple[str, ...]) -> list[Capability]:
    caps: list[Capability] = []
    for name in names:
        module = importlib.import_module(f"{_PKG}.{name}.capability")
        cap = module.get_capability()
        if cap.name != name:
            raise ValueError(f"capability {name} reports name={cap.name!r}")
        caps.append(cap)
        log.info("capability.loaded", name=name, tools=len(cap.tools()))
    return caps


def migration_dirs(names: list[str] | tuple[str, ...]) -> dict[str, Path]:
    base = Path(__file__).parent
    return {name: base / name / "migrations" for name in names}
