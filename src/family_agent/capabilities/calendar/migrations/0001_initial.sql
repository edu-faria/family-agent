CREATE TABLE IF NOT EXISTS appointment (
    id                    INTEGER PRIMARY KEY,
    title                 TEXT    NOT NULL,
    starts_at             TEXT    NOT NULL,          -- ISO-8601 UTC
    ends_at               TEXT    NOT NULL,          -- ISO-8601 UTC (default: starts_at + 1h)
    all_day               INTEGER NOT NULL DEFAULT 0,
    location              TEXT,
    notes                 TEXT,
    owner_member_id       INTEGER,
    attendees_json        TEXT    NOT NULL DEFAULT '[]',
    car_needed            TEXT    NOT NULL DEFAULT 'unknown',   -- yes | no | maybe | unknown
    driver_member_id      INTEGER,
    travel_buffer_minutes INTEGER,                              -- NULL -> use config default
    rrule                 TEXT,                                 -- optional, e.g. 'FREQ=WEEKLY'
    created_by            INTEGER,
    source                TEXT    NOT NULL DEFAULT 'chat',
    created_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_appt_start ON appointment (starts_at);

-- Reminder rows exist now; the scheduler that sends them is a future feature.
CREATE TABLE IF NOT EXISTS appointment_reminder (
    id             INTEGER PRIMARY KEY,
    appointment_id INTEGER NOT NULL REFERENCES appointment(id) ON DELETE CASCADE,
    offset_minutes INTEGER NOT NULL,        -- minutes before starts_at
    sent_at        TEXT
);
