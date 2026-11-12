"""T14 — reply/conversation tracking.

Two paths, one storage mechanism (dm_events):
- automated (SHOULD tier, needs T07 + dm.read entitlement): ingest_reply_events
  pulls authorized DM events and links inbound messages to prospect + attempt,
  idempotent on the API event id.
- manual (MUST tier, active until automated is verified — decision D4):
  record_manual_reply writes a synthetic dm_event (manual- prefixed id).

The UI labels which mode is active and never claims real-time monitoring.
"""

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from src.db import store
from src.integrations.x_client import DMEventPayload, XClient
from src.models import DMEvent


def _latest_attempt_id(conn: sqlite3.Connection, prospect_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM outreach_attempts WHERE prospect_id = ? ORDER BY id DESC LIMIT 1",
        (prospect_id,),
    ).fetchone()
    return row["id"] if row else None


def record_manual_reply(conn: sqlite3.Connection, prospect_id: int,
                        text: str | None = None) -> int:
    """Operator-recorded reply (manual tracking path). Linked to the prospect and,
    when one exists, to their most recent outreach attempt."""
    prospect = store.get_prospect(conn, prospect_id)
    if prospect is None:
        raise ValueError(f"unknown prospect {prospect_id}")
    return store.insert_dm_event(conn, DMEvent(
        x_dm_event_id=f"manual-{uuid4().hex[:12]}",
        prospect_id=prospect_id,
        outreach_attempt_id=_latest_attempt_id(conn, prospect_id),
        conversation_id=None,
        event_type="MessageCreate",
        sender_x_user_id=prospect["x_user_id"],
        text=text,
        occurred_at=datetime.now(UTC).isoformat(timespec="seconds"),
    ))


def ingest_reply_events(conn: sqlite3.Connection, client: XClient) -> int:
    """Pull authorized DM events and store inbound replies (automated path).

    Inbound = MessageCreate whose sender is a known prospect (the operator's own
    outbound messages are not prospect senders). Unknown senders are skipped —
    nothing is linked or claimed without a prospect. Returns new events stored.
    """
    events: list[DMEventPayload] = client.get_dm_events()
    known = {
        row["x_user_id"]: row["id"]
        for row in conn.execute("SELECT id, x_user_id FROM prospects").fetchall()
    }
    new_count = 0
    for ev in events:
        if ev.event_type != "MessageCreate" or ev.sender_id not in known:
            continue
        stored = store.insert_dm_event(conn, DMEvent(
            x_dm_event_id=ev.id,
            prospect_id=known[ev.sender_id],
            outreach_attempt_id=_latest_attempt_id(conn, known[ev.sender_id]),
            conversation_id=ev.conversation_id,
            event_type=ev.event_type,
            sender_x_user_id=ev.sender_id,
            text=ev.text,
            occurred_at=ev.created_at,
        ))
        if stored:
            new_count += 1
    return new_count


def latest_replies_for_prospect(conn: sqlite3.Connection, prospect_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM dm_events WHERE prospect_id = ? AND event_type = 'MessageCreate' "
        "ORDER BY ingested_at DESC, id DESC",
        (prospect_id,),
    ).fetchall()
