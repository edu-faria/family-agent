from __future__ import annotations

from family_agent.persistence.db import Database
from family_agent.tools.registry import ToolError


class ShoppingRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_id(self, name: str) -> int:
        row = self.db.query_one("SELECT id FROM shopping_list WHERE name=? AND active=1", (name,))
        if row:
            return int(row["id"])
        return self.db.execute("INSERT INTO shopping_list (name) VALUES (?)", (name,))

    def add_item(self, list_id: int, member_id: int, **f) -> int:
        return self.db.execute(
            "INSERT INTO shopping_item (list_id, name, qty, unit, category, needed_by, added_by) "
            "VALUES (?,?,?,?,?,?,?)",
            (list_id, f["name"], f.get("qty"), f.get("unit"), f.get("category"),
             f.get("needed_by"), member_id),
        )

    def set_status(self, list_id: int, names: list[str], status: str) -> int:
        n = 0
        for name in names:
            n += self.db.execute(
                "UPDATE shopping_item SET status=?, "
                "bought_at=CASE WHEN ?='bought' THEN datetime('now') ELSE bought_at END "
                "WHERE list_id=? AND lower(name)=lower(?) AND status='needed'",
                (status, status, list_id, name),
            ) or 0
        return n

    def items(self, list_id: int, include_bought: bool) -> list[dict]:
        sql = "SELECT * FROM shopping_item WHERE list_id=? AND status!='removed'"
        if not include_bought:
            sql += " AND status='needed'"
        sql += " ORDER BY category, name"
        return [dict(r) for r in self.db.query(sql, (list_id,))]
