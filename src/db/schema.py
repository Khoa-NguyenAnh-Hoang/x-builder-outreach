"""SQLite schema v1 (T05). Explicit versioning: PRAGMA user_version.

Bump SCHEMA_VERSION and extend _migrate for any future schema change; init_db is
repeatable and never drops existing tables at the current version.
"""

import sqlite3

SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE prospects (
    id             INTEGER PRIMARY KEY,
    x_user_id      TEXT NOT NULL UNIQUE,
    username       TEXT,
    display_name   TEXT,
    bio            TEXT,
    follower_count INTEGER,
    source         TEXT NOT NULL,        -- seed | search | manual
    source_query   TEXT,
    first_seen_at  TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE evidence (
    id          INTEGER PRIMARY KEY,
    prospect_id INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    source_type TEXT NOT NULL,            -- post | profile | bio_link
    text        TEXT,
    captured_at TEXT NOT NULL,
    UNIQUE (prospect_id, url)             -- re-discovery updates, never duplicates
);

CREATE TABLE qualification_results (
    id          INTEGER PRIMARY KEY,
    prospect_id INTEGER NOT NULL UNIQUE REFERENCES prospects(id) ON DELETE CASCADE,
    score       REAL NOT NULL,
    components  TEXT NOT NULL,            -- JSON {relevance, role, contribution, freshness}
    reasons     TEXT NOT NULL,            -- JSON list[str]
    confidence  TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
    computed_at TEXT NOT NULL
);

CREATE TABLE consent_records (
    id           INTEGER PRIMARY KEY,
    prospect_id  INTEGER NOT NULL UNIQUE REFERENCES prospects(id) ON DELETE CASCADE,
    source       TEXT NOT NULL,
    evidence_url TEXT,
    captured_at  TEXT NOT NULL,
    scope        TEXT NOT NULL,
    verified_by  TEXT,
    verified_at  TEXT,
    opted_out_at TEXT                    -- NOT NULL => opted out (invariant I2)
);

CREATE TABLE drafts (
    id            INTEGER PRIMARY KEY,
    prospect_id   INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    text          TEXT NOT NULL,
    evidence_refs TEXT NOT NULL,          -- JSON [{claim, evidence_id}]
    generator     TEXT NOT NULL,          -- template | llm:<name>
    status        TEXT NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'approved', 'rejected', 'superseded')),
    approved_at   TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE outreach_attempts (
    id               INTEGER PRIMARY KEY,
    prospect_id      INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
    draft_id         INTEGER NOT NULL REFERENCES drafts(id),
    mode             TEXT NOT NULL CHECK (mode IN ('dev_test', 'operator_approved', 'automated_batch')),
    status           TEXT NOT NULL DEFAULT 'intent'
                     CHECK (status IN ('intent', 'sent', 'failed', 'unknown')),
    deny_reason      TEXT,                -- set when status='failed' from an eligibility DENY
    x_conversation_id TEXT,
    x_event_id       TEXT,
    requested_at     TEXT NOT NULL,
    resolved_at      TEXT
);

-- Invariant I7 as a database guarantee: one *active* attempt per recipient.
CREATE UNIQUE INDEX ux_outreach_active ON outreach_attempts (prospect_id)
    WHERE status IN ('intent', 'sent', 'unknown');

CREATE TABLE dm_events (
    id                  INTEGER PRIMARY KEY,
    x_dm_event_id       TEXT NOT NULL UNIQUE,   -- idempotent ingestion from the API
    prospect_id         INTEGER REFERENCES prospects(id),
    outreach_attempt_id INTEGER REFERENCES outreach_attempts(id),
    conversation_id     TEXT,
    event_type          TEXT NOT NULL,          -- MessageCreate | ParticipantsJoin | ParticipantsLeave
    sender_x_user_id    TEXT,
    text                TEXT,
    occurred_at         TEXT,
    ingested_at         TEXT NOT NULL
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Create the schema if absent; safe to call on every startup."""
    (version,) = conn.execute("PRAGMA user_version").fetchone()
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema v{version} is newer than this app (v{SCHEMA_VERSION}); "
            "update the application before opening this database."
        )
    conn.executescript(_SCHEMA_SQL)
    # PRAGMA cannot be parameterized; SCHEMA_VERSION is an internal int constant.
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
