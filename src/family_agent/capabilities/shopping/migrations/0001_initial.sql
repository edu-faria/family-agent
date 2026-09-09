CREATE TABLE IF NOT EXISTS shopping_list (
    id      INTEGER PRIMARY KEY,
    name    TEXT    NOT NULL UNIQUE,
    active  INTEGER NOT NULL DEFAULT 1
);

INSERT OR IGNORE INTO shopping_list (id, name) VALUES (1, 'Supermercado');

CREATE TABLE IF NOT EXISTS shopping_item (
    id        INTEGER PRIMARY KEY,
    list_id   INTEGER NOT NULL REFERENCES shopping_list(id) ON DELETE CASCADE,
    name      TEXT    NOT NULL,
    qty       REAL,
    unit      TEXT,
    category  TEXT,
    needed_by TEXT,                                  -- optional ISO date; hook for "buy before X"
    status    TEXT    NOT NULL DEFAULT 'needed',     -- needed | bought | removed
    added_by  INTEGER,
    added_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    bought_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_item_list_status ON shopping_item (list_id, status);
