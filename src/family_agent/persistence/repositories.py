"""Shared repositories: members, conversation history, audit log, pending actions.

Capability-specific repositories live inside each capability package.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from family_agent.persistence.db import Database
from family_agent.types import PendingAction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemberRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert(self, telegram_user_id: int, display_name: str, locale: str) -> int:
        self.db.execute(
            "INSERT INTO family_member (telegram_user_id, display_name, locale) VALUES (?,?,?) "
            "ON CONFLICT(telegram_user_id) DO UPDATE SET display_name=excluded.display_name",
            (telegram_user_id, display_name, locale),
        )
        row = self.db.query_one(
            "SELECT id FROM family_member WHERE telegram_user_id=?", (telegram_user_id,)
        )
        assert row is not None
        return int(row["id"])

    def all_active(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query("SELECT * FROM family_member WHERE active=1")]


class ConversationRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def append(self, chat_id: int, member_id: int | None, role: str, content: str) -> None:
        self.db.execute(
            "INSERT INTO conversation_turn (chat_id, member_id, role, content) VALUES (?,?,?,?)",
            (chat_id, member_id, role, content),
        )

    def recent(self, chat_id: int, limit: int) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT role, content, ts FROM conversation_turn WHERE chat_id=? "
            "ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        )
        return [dict(r) for r in reversed(rows)]


class AuditRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record(
        self,
        *,
        kind: str,
        member_id: int | None = None,
        chat_id: int | None = None,
        tool_name: str | None = None,
        model: str | None = None,
        input_obj: Any = None,
        result_summary: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        self.db.execute(
            "INSERT INTO audit_log (kind, member_id, chat_id, tool_name, model, input_json, "
            "result_summary, input_tokens, output_tokens, cost_usd) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                kind,
                member_id,
                chat_id,
                tool_name,
                model,
                json.dumps(input_obj, default=str) if input_obj is not None else None,
                result_summary,
                input_tokens,
                output_tokens,
                cost_usd,
            ),
        )

    def messages_today(self, member_id: int) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) c FROM audit_log WHERE kind='inbound' AND member_id=? "
            "AND ts >= datetime('now','start of day')",
            (member_id,),
        )
        return int(row["c"]) if row else 0

    def messages_today_global(self) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) c FROM audit_log WHERE kind='inbound' "
            "AND ts >= datetime('now','start of day')"
        )
        return int(row["c"]) if row else 0

    def spend_this_month(self, member_id: int | None = None) -> float:
        if member_id is None:
            row = self.db.query_one(
                "SELECT COALESCE(SUM(cost_usd),0) s FROM audit_log "
                "WHERE ts >= datetime('now','start of month')"
            )
        else:
            row = self.db.query_one(
                "SELECT COALESCE(SUM(cost_usd),0) s FROM audit_log "
                "WHERE member_id=? AND ts >= datetime('now','start of month')",
                (member_id,),
            )
        return float(row["s"]) if row else 0.0


class PendingActionRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, action: PendingAction) -> None:
        self.db.execute(
            "INSERT INTO pending_action (token, chat_id, member_id, tool_name, tool_input, "
            "human_summary, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                action.token,
                action.chat_id,
                action.member_id,
                action.tool_name,
                json.dumps(action.tool_input, default=str),
                action.human_summary,
                action.created_at.isoformat(),
            ),
        )

    def get(self, token: str) -> PendingAction | None:
        row = self.db.query_one(
            "SELECT * FROM pending_action WHERE token=? AND resolved_at IS NULL", (token,)
        )
        if not row:
            return None
        return PendingAction(
            token=row["token"],
            chat_id=row["chat_id"],
            member_id=row["member_id"],
            tool_name=row["tool_name"],
            tool_input=json.loads(row["tool_input"]),
            human_summary=row["human_summary"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def resolve(self, token: str, decision: str) -> None:
        self.db.execute(
            "UPDATE pending_action SET resolved_at=?, decision=? WHERE token=?",
            (_now(), decision, token),
        )

    def latest_open_for_chat(self, chat_id: int) -> PendingAction | None:
        row = self.db.query_one(
            "SELECT token FROM pending_action WHERE chat_id=? AND resolved_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (chat_id,),
        )
        return self.get(row["token"]) if row else None
