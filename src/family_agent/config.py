"""Configuration: non-secret values from config.toml, secrets + overrides from the env.

Override any config.toml value with an env var named FAMILY_AGENT_<UPPER_DOTTED_PATH>,
double underscore for nesting, e.g. FAMILY_AGENT_AGENT__PRIMARY_MODEL=claude-sonnet-5.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("FAMILY_AGENT_CONFIG", "config.toml"))


@dataclass(frozen=True)
class Member:
    telegram_user_id: int
    display_name: str
    locale: str = "pt"


@dataclass(frozen=True)
class AgentConfig:
    primary_model: str = "claude-opus-5"
    fallback_model: str = "gpt-4o"
    router_model: str = "claude-haiku-4-5"
    max_tool_calls_per_turn: int = 6
    turn_timeout_seconds: int = 60
    max_output_tokens: int = 1200
    history_turns: int = 15


@dataclass(frozen=True)
class Limits:
    per_member_daily_messages: int = 100
    global_daily_messages: int = 400
    per_member_monthly_usd: float = 15.0
    global_monthly_usd: float = 40.0
    max_inbound_chars: int = 2000


@dataclass(frozen=True)
class Settings:
    timezone: str = "Europe/Berlin"
    default_locale: str = "pt"
    enabled_capabilities: tuple[str, ...] = ("calendar", "shopping")
    db_path: Path = Path("/data/family.db")
    log_level: str = "INFO"

    telegram_bot_token: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    allowlist: frozenset[int] = frozenset()
    members: dict[int, Member] = field(default_factory=dict)

    agent: AgentConfig = field(default_factory=AgentConfig)
    limits: Limits = field(default_factory=Limits)
    calendar_travel_buffer_minutes: int = 15
    backup_keep_days: int = 14

    def member(self, telegram_user_id: int) -> Member | None:
        return self.members.get(telegram_user_id)


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    return v.strip() if v else None


def _parse_allowlist(raw: str | None) -> frozenset[int]:
    if not raw:
        return frozenset()
    return frozenset(int(x) for x in raw.replace(" ", "").split(",") if x)


def _parse_members(raw: str | None, default_locale: str) -> dict[int, Member]:
    out: dict[int, Member] = {}
    if not raw:
        return out
    for chunk in raw.split(","):
        parts = chunk.split(":")
        if len(parts) < 2:
            continue
        uid = int(parts[0])
        name = parts[1]
        locale = parts[2] if len(parts) > 2 else default_locale
        out[uid] = Member(uid, name, locale)
    return out


def load_settings(path: Path | None = None) -> Settings:
    path = path or CONFIG_PATH
    raw: dict = {}
    if path.exists():
        raw = tomllib.loads(path.read_text())

    # env override helper for a dotted toml path
    def cfg(dotted: str, default):
        node: object = raw
        for part in dotted.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        env_name = "FAMILY_AGENT_" + dotted.upper().replace(".", "__")
        env_val = _env(env_name)
        if env_val is not None:
            return type(default)(env_val) if not isinstance(default, (list, tuple)) else env_val.split(",")
        return node if node is not None else default

    default_locale = str(cfg("default_locale", "pt"))
    agent_raw = raw.get("agent", {})
    limits_raw = raw.get("limits", {})

    agent = AgentConfig(
        primary_model=str(cfg("agent.primary_model", AgentConfig.primary_model)),
        fallback_model=str(cfg("agent.fallback_model", AgentConfig.fallback_model)),
        router_model=str(cfg("agent.router_model", AgentConfig.router_model)),
        max_tool_calls_per_turn=int(agent_raw.get("max_tool_calls_per_turn", 6)),
        turn_timeout_seconds=int(agent_raw.get("turn_timeout_seconds", 60)),
        max_output_tokens=int(agent_raw.get("max_output_tokens", 1200)),
        history_turns=int(agent_raw.get("history_turns", 15)),
    )
    limits = Limits(
        per_member_daily_messages=int(limits_raw.get("per_member_daily_messages", 100)),
        global_daily_messages=int(limits_raw.get("global_daily_messages", 400)),
        per_member_monthly_usd=float(limits_raw.get("per_member_monthly_usd", 15.0)),
        global_monthly_usd=float(limits_raw.get("global_monthly_usd", 40.0)),
        max_inbound_chars=int(limits_raw.get("max_inbound_chars", 2000)),
    )

    return Settings(
        timezone=str(cfg("timezone", "Europe/Berlin")),
        default_locale=default_locale,
        enabled_capabilities=tuple(cfg("enabled_capabilities", ["calendar", "shopping"])),
        db_path=Path(_env("FAMILY_AGENT_DB_PATH") or "/data/family.db"),
        log_level=_env("FAMILY_AGENT_LOG_LEVEL") or "INFO",
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN") or "",
        anthropic_api_key=_env("ANTHROPIC_API_KEY") or "",
        openai_api_key=_env("OPENAI_API_KEY") or "",
        allowlist=_parse_allowlist(_env("FAMILY_ALLOWLIST")),
        members=_parse_members(_env("FAMILY_MEMBERS"), default_locale),
        agent=agent,
        limits=limits,
        calendar_travel_buffer_minutes=int(raw.get("calendar", {}).get("travel_buffer_minutes", 15)),
        backup_keep_days=int(raw.get("backup", {}).get("keep_days", 14)),
    )
