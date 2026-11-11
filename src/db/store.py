"""Data-access functions for src/db. Each takes an open connection; no global state."""

import json
import sqlite3
from datetime import datetime, timezone

from src.models import ConsentRecord, Draft, DMEvent, Evidence, Prospect, Qualification


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def upsert_prospect(conn: sqlite3.Connection, p: Prospect) -> int:
    (prospect_id,) = conn.execute(
        """
        INSERT INTO prospects
            (x_user_id, username, display_name, bio, follower_count,
             source, source_query, first_seen_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(x_user_id) DO UPDATE SET
            username = excluded.username,
            display_name = excluded.display_name,
            bio = excluded.bio,
            follower_count = excluded.follower_count,
            source = excluded.source,
            source_query = excluded.source_query,
            updated_at = excluded.updated_at
        RETURNING id
        """,
        (p.x_user_id, p.username, p.display_name, p.bio, p.follower_count,
         p.source, p.source_query, now_iso(), now_iso()),
    ).fetchone()
    conn.commit()
    return prospect_id


def get_prospect_by_x_user_id(conn: sqlite3.Connection, x_user_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM prospects WHERE x_user_id = ?", (x_user_id,)
    ).fetchone()


def upsert_evidence(conn: sqlite3.Connection, e: Evidence) -> int:
    (evidence_id,) = conn.execute(
        """
        INSERT INTO evidence (prospect_id, url, source_type, text, captured_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(prospect_id, url) DO UPDATE SET
            text = excluded.text,
            captured_at = excluded.captured_at
        RETURNING id
        """,
        (e.prospect_id, e.url, e.source_type, e.text, now_iso()),
    ).fetchone()
    conn.commit()
    return evidence_id


def save_qualification(conn: sqlite3.Connection, q: Qualification) -> int:
    (qual_id,) = conn.execute(
        """
        INSERT INTO qualification_results
            (prospect_id, score, components, reasons, confidence, computed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(prospect_id) DO UPDATE SET
            score = excluded.score,
            components = excluded.components,
            reasons = excluded.reasons,
            confidence = excluded.confidence,
            computed_at = excluded.computed_at
        RETURNING id
        """,
        (q.prospect_id, q.score, json.dumps(q.components), json.dumps(q.reasons),
         q.confidence, now_iso()),
    ).fetchone()
    conn.commit()
    return qual_id


def upsert_consent(conn: sqlite3.Connection, c: ConsentRecord) -> int:
    (consent_id,) = conn.execute(
        """
        INSERT INTO consent_records
            (prospect_id, source, evidence_url, captured_at, scope,
             verified_by, verified_at, opted_out_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(prospect_id) DO UPDATE SET
            source = excluded.source,
            evidence_url = excluded.evidence_url,
            captured_at = excluded.captured_at,
            scope = excluded.scope,
            verified_by = excluded.verified_by,
            verified_at = excluded.verified_at,
            opted_out_at = excluded.opted_out_at
        RETURNING id
        """,
        (c.prospect_id, c.source, c.evidence_url, now_iso(), c.scope,
         c.verified_by, c.verified_at, c.opted_out_at),
    ).fetchone()
    conn.commit()
    return consent_id


def is_opted_out(conn: sqlite3.Connection, prospect_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM consent_records WHERE prospect_id = ? AND opted_out_at IS NOT NULL",
        (prospect_id,),
    ).fetchone() is not None


def create_draft(conn: sqlite3.Connection, d: Draft) -> int:
    (draft_id,) = conn.execute(
        """
        INSERT INTO drafts (prospect_id, text, evidence_refs, generator, status, created_at)
        VALUES (?, ?, ?, ?, 'draft', ?)
        RETURNING id
        """,
        (d.prospect_id, d.text, json.dumps(d.evidence_refs), d.generator, now_iso()),
    ).fetchone()
    conn.commit()
    return draft_id


def set_draft_status(
    conn: sqlite3.Connection, draft_id: int, status: str, approved_at: str | None = None
) -> None:
    conn.execute(
        "UPDATE drafts SET status = ?, approved_at = COALESCE(?, approved_at) WHERE id = ?",
        (status, approved_at, draft_id),
    )
    conn.commit()


def create_send_intent(
    conn: sqlite3.Connection, prospect_id: int, draft_id: int, mode: str
) -> int:
    """Persist the send intent BEFORE the API call (I7).

    Raises sqlite3.IntegrityError if an active attempt (intent/sent/unknown)
    already exists for the recipient — the DB backstop for duplicate sends.
    """
    (attempt_id,) = conn.execute(
        """
        INSERT INTO outreach_attempts (prospect_id, draft_id, mode, status, requested_at)
        VALUES (?, ?, ?, 'intent', ?)
        RETURNING id
        """,
        (prospect_id, draft_id, mode, now_iso()),
    ).fetchone()
    conn.commit()
    return attempt_id


def resolve_send_attempt(
    conn: sqlite3.Connection,
    attempt_id: int,
    status: str,  # sent | failed | unknown
    x_conversation_id: str | None = None,
    x_event_id: str | None = None,
    deny_reason: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE outreach_attempts
        SET status = ?, x_conversation_id = COALESCE(?, x_conversation_id),
            x_event_id = COALESCE(?, x_event_id), deny_reason = ?,
            resolved_at = ?
        WHERE id = ?
        """,
        (status, x_conversation_id, x_event_id, deny_reason, now_iso(), attempt_id),
    )
    conn.commit()


def record_denied_send(
    conn: sqlite3.Connection, prospect_id: int, draft_id: int, mode: str, deny_reason: str
) -> int:
    """Store an eligibility DENY as a resolved failed attempt (A3: reasons are kept and shown).

    'failed' is outside the active-status set, so a denial never blocks later legitimate sends.
    """
    (attempt_id,) = conn.execute(
        """
        INSERT INTO outreach_attempts
            (prospect_id, draft_id, mode, status, deny_reason, requested_at, resolved_at)
        VALUES (?, ?, ?, 'failed', ?, ?, ?)
        RETURNING id
        """,
        (prospect_id, draft_id, mode, deny_reason, now_iso(), now_iso()),
    ).fetchone()
    conn.commit()
    return attempt_id


def has_active_attempt(conn: sqlite3.Connection, prospect_id: int) -> bool:
    return conn.execute(
        """
        SELECT 1 FROM outreach_attempts
        WHERE prospect_id = ? AND status IN ('intent', 'sent', 'unknown')
        """,
        (prospect_id,),
    ).fetchone() is not None


def insert_dm_event(conn: sqlite3.Connection, ev: DMEvent) -> bool:
    """Idempotent on the API event id; returns True if a new row was written."""
    cur = conn.execute(
        """
        INSERT INTO dm_events
            (x_dm_event_id, prospect_id, outreach_attempt_id, conversation_id,
             event_type, sender_x_user_id, text, occurred_at, ingested_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(x_dm_event_id) DO NOTHING
        """,
        (ev.x_dm_event_id, ev.prospect_id, ev.outreach_attempt_id, ev.conversation_id,
         ev.event_type, ev.sender_x_user_id, ev.text, ev.occurred_at, now_iso()),
    )
    conn.commit()
    return cur.rowcount == 1
