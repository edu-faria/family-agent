"""Calendar persistence + datetime handling. No LLM concerns here."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil import parser as dtparse

from family_agent.capabilities.calendar.conflicts import ApptView
from family_agent.persistence.db import Database
from family_agent.tools.registry import ToolError


def parse_local(text: str, tz: str) -> datetime:
    """Parse a user/LLM datetime string and return an aware UTC datetime."""
    try:
        dt = dtparse.parse(text, dayfirst=False)
    except (ValueError, OverflowError) as exc:
        raise ToolError(f"Não entendi a data/hora '{text}'.") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(ZoneInfo("UTC"))


def to_local_str(iso_utc: str, tz: str) -> str:
    dt = datetime.fromisoformat(iso_utc).astimezone(ZoneInfo(tz))
    return dt.strftime("%a %d/%m %H:%M")


class CalendarRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(self, **fields) -> int:
        return self.db.execute(
            "INSERT INTO appointment (title, starts_at, ends_at, all_day, location, notes, "
            "owner_member_id, attendees_json, car_needed, driver_member_id, rrule, created_by) "
            "VALUES (:title,:starts_at,:ends_at,:all_day,:location,:notes,:owner_member_id,"
            ":attendees_json,:car_needed,:driver_member_id,:rrule,:created_by)",
            fields,
        )

    def get(self, appt_id: int) -> dict | None:
        row = self.db.query_one("SELECT * FROM appointment WHERE id=?", (appt_id,))
        return dict(row) if row else None

    def update(self, appt_id: int, changes: dict) -> None:
        if not changes:
            return
        cols = ", ".join(f"{k}=:{k}" for k in changes)
        changes = {**changes, "id": appt_id}
        self.db.execute(
            f"UPDATE appointment SET {cols}, updated_at=datetime('now') WHERE id=:id", changes
        )

    def delete(self, appt_id: int) -> None:
        self.db.execute("DELETE FROM appointment WHERE id=?", (appt_id,))

    def in_range(self, start_utc: str, end_utc: str, query: str | None = None) -> list[dict]:
        sql = "SELECT * FROM appointment WHERE starts_at < ? AND ends_at > ? "
        params: list = [end_utc, start_utc]
        if query:
            sql += "AND (title LIKE ? OR IFNULL(location,'') LIKE ? OR IFNULL(notes,'') LIKE ?) "
            like = f"%{query}%"
            params += [like, like, like]
        sql += "ORDER BY starts_at"
        return [dict(r) for r in self.db.query(sql, params)]

    def same_day(self, day_start_utc: str, day_end_utc: str) -> list[dict]:
        return [
            dict(r)
            for r in self.db.query(
                "SELECT * FROM appointment WHERE starts_at < ? AND ends_at > ? ORDER BY starts_at",
                (day_end_utc, day_start_utc),
            )
        ]


def row_to_view(row: dict) -> ApptView:
    return ApptView(
        id=row["id"],
        title=row["title"],
        start=datetime.fromisoformat(row["starts_at"]),
        end=datetime.fromisoformat(row["ends_at"]),
        car_needed=row.get("car_needed", "unknown"),
        location=row.get("location"),
        attendees=tuple(json.loads(row.get("attendees_json") or "[]")),
    )


def default_end(start_utc: datetime) -> datetime:
    return start_utc + timedelta(hours=1)
