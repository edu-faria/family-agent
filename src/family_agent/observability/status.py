"""Small helpers for an admin `/status`-style summary (wire into the gateway later)."""

from __future__ import annotations

from family_agent.persistence.db import Database


def status_summary(db: Database) -> str:
    row = db.query_one(
        "SELECT "
        " (SELECT COUNT(*) FROM audit_log WHERE kind='inbound' AND ts >= datetime('now','start of day')) msgs_today,"
        " (SELECT COALESCE(SUM(cost_usd),0) FROM audit_log WHERE ts >= datetime('now','start of day')) spend_today,"
        " (SELECT COALESCE(SUM(cost_usd),0) FROM audit_log WHERE ts >= datetime('now','start of month')) spend_month,"
        " (SELECT COUNT(*) FROM appointment WHERE starts_at >= datetime('now')) upcoming"
    )
    if row is None:
        return "no data"
    return (
        f"mensagens hoje: {row['msgs_today']}\n"
        f"gasto hoje: ${row['spend_today']:.2f}\n"
        f"gasto no mês: ${row['spend_month']:.2f}\n"
        f"compromissos futuros: {row['upcoming']}"
    )
