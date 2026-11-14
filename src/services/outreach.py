"""T13 — safe, duplicate-resistant sending. The whole chain in one callable:

  eligibility gate (A3) → persist send-intent (I7) → official send_dm →
  resolve status → consume approval (I1)

Resolution rules:
- success → 'sent' (+ message ids), approval consumed
- timeout / malformed response → 'unknown' (a message MAY exist) — approval
  consumed too, so nothing re-sends until the operator reconciles and re-approves
- auth / rate-limit / unavailable / other definitive errors → 'failed' (nothing
  was sent) — approval retained so the operator can deliberately retry
- gate denial → denial recorded (reason = the failing check), API never called
"""

import sqlite3

from pydantic import BaseModel

from src.config import Settings
from src.db import store
from src.integrations.x_client import (
    MalformedResponseError,
    RequestTimeout,
    XClient,
    XClientError,
)
from src.services.consent import consume_approval, evaluate_send_eligibility


class SendOutcome(BaseModel):
    status: str  # sent | unknown | failed | denied
    attempt_id: int | None = None
    message_id: str | None = None
    conversation_id: str | None = None
    error: str | None = None
    deny_reason: str | None = None


def send_approved_draft(conn: sqlite3.Connection, client: XClient, prospect_id: int,
                        settings: Settings, mode: str, *,
                        now=None, api_available: bool = True) -> SendOutcome:
    decision = evaluate_send_eligibility(conn, prospect_id, mode, settings,
                                         now=now, api_available=api_available)
    latest_draft = conn.execute(
        "SELECT id, text FROM drafts WHERE prospect_id = ? ORDER BY id DESC LIMIT 1",
        (prospect_id,),
    ).fetchone()

    if not decision.allowed:
        if latest_draft:  # no draft row at all -> nothing to attach a denial to
            store.record_denied_send(conn, prospect_id, latest_draft["id"], mode,
                                     decision.reason)
        return SendOutcome(status="denied", deny_reason=decision.reason)

    draft_id, text = latest_draft["id"], latest_draft["text"]
    recipient = conn.execute("SELECT x_user_id FROM prospects WHERE id = ?",
                             (prospect_id,)).fetchone()[0]

    try:
        attempt_id = store.create_send_intent(conn, prospect_id, draft_id, mode)
    except sqlite3.IntegrityError as err:
        # database backstop for a race the gate missed — one logical send, ever (I7)
        return SendOutcome(status="denied", deny_reason="duplicate (database guard)",
                           error=str(err))

    try:
        result = client.send_dm(recipient, text)
    except (RequestTimeout, MalformedResponseError) as err:
        # ambiguous: the request may have been delivered — reconcile, never blind-retry
        store.resolve_send_attempt(conn, attempt_id, "unknown")
        consume_approval(conn, prospect_id)
        return SendOutcome(status="unknown", attempt_id=attempt_id, error=str(err))
    except XClientError as err:
        # definitive: nothing was sent. deny_reason stays NULL so the dashboard's
        # attention list flags this as a real failure needing investigation
        store.resolve_send_attempt(conn, attempt_id, "failed")
        return SendOutcome(status="failed", attempt_id=attempt_id, error=str(err))

    store.resolve_send_attempt(conn, attempt_id, "sent",
                               x_conversation_id=result.dm_conversation_id,
                               x_event_id=result.dm_event_id)
    consume_approval(conn, prospect_id)  # I1: one send per approval
    return SendOutcome(status="sent", attempt_id=attempt_id,
                       message_id=result.dm_event_id,
                       conversation_id=result.dm_conversation_id)
