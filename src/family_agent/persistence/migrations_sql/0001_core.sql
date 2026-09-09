-- Core tables shared by every capability.

CREATE TABLE IF NOT EXISTS family_member (
    id                INTEGER PRIMARY KEY,
    telegram_user_id  INTEGER NOT NULL UNIQUE,
    display_name      TEXT    NOT NULL,
    role              TEXT    NOT NULL DEFAULT 'member',   -- 'member' | 'admin'
    locale            TEXT    NOT NULL DEFAULT 'pt',
    active            INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Rolling chat history; trimmed to config.agent.history_turns on read.
CREATE TABLE IF NOT EXISTS conversation_turn (
    id          INTEGER PRIMARY KEY,
    chat_id     INTEGER NOT NULL,
    member_id   INTEGER,
    role        TEXT    NOT NULL,          -- 'user' | 'assistant'
    content     TEXT    NOT NULL,
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_turn_chat_ts ON conversation_turn (chat_id, ts);

-- Every inbound message, tool call, model call and confirmation decision.
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY,
    ts              TEXT    NOT NULL DEFAULT (datetime('now')),
    member_id       INTEGER,
    chat_id         INTEGER,
    kind            TEXT    NOT NULL,      -- 'inbound' | 'model' | 'tool' | 'confirm' | 'refusal' | 'error'
    tool_name       TEXT,
    model           TEXT,
    input_json      TEXT,
    result_summary  TEXT,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd        REAL    NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log (ts);
CREATE INDEX IF NOT EXISTS ix_audit_member_ts ON audit_log (member_id, ts);

-- Proposed writes waiting on a family Yes/No.
CREATE TABLE IF NOT EXISTS pending_action (
    token         TEXT PRIMARY KEY,
    chat_id       INTEGER NOT NULL,
    member_id     INTEGER NOT NULL,
    tool_name     TEXT    NOT NULL,
    tool_input    TEXT    NOT NULL,       -- JSON
    human_summary TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    resolved_at   TEXT,
    decision      TEXT                     -- 'confirmed' | 'rejected' | 'expired'
);
