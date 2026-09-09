"""Tiny forward-only migration runner.

Core migrations live in `migrations_sql/`. Each capability contributes its own
`.sql` files (see capabilities/*/migrations/). Files are applied in lexical order
of `<namespace>:<filename>` and recorded in `schema_migrations`.
"""

from __future__ import annotations

from pathlib import Path

from family_agent.logging_setup import get_logger
from family_agent.persistence.db import Database

log = get_logger(__name__)

_CORE_DIR = Path(__file__).parent / "migrations_sql"


def _applied(db: Database) -> set[str]:
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(id TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    return {r["id"] for r in db.query("SELECT id FROM schema_migrations")}


def _apply_dir(db: Database, namespace: str, directory: Path, done: set[str]) -> None:
    if not directory.is_dir():
        return
    for sql_file in sorted(directory.glob("*.sql")):
        mig_id = f"{namespace}:{sql_file.name}"
        if mig_id in done:
            continue
        log.info("migration.apply", id=mig_id)
        with db.transaction() as conn:
            conn.executescript(sql_file.read_text())
            conn.execute("INSERT INTO schema_migrations (id) VALUES (?)", (mig_id,))
        done.add(mig_id)


def run_migrations(db: Database, capability_dirs: dict[str, Path]) -> None:
    """`capability_dirs` maps capability name -> its migrations directory."""
    done = _applied(db)
    _apply_dir(db, "core", _CORE_DIR, done)
    for name, path in capability_dirs.items():
        _apply_dir(db, name, path, done)
    log.info("migration.done", count=len(done))
