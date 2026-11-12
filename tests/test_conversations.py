import pytest

from src.db import connect, init_db, store
from src.integrations.fake_x_client import FakeXClient
from src.integrations.x_client import DMEventPayload, EndpointUnavailable
from src.models import Draft, Prospect
from src.services.conversations import (
    ingest_reply_events,
    latest_replies_for_prospect,
    record_manual_reply,
)


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def _prospect_with_attempt(conn, x_user_id="100", username="robo") -> tuple[int, int]:
    pid = store.upsert_prospect(conn, Prospect(
        x_user_id=x_user_id, username=username, source="seed"))
    did = store.create_draft(conn, Draft(
        prospect_id=pid, text="Hi!", evidence_refs=[], generator="template"))
    aid = store.create_send_intent(conn, pid, did, "operator_approved")
    return pid, aid


# --- manual path (MUST tier) -------------------------------------------------

def test_manual_reply_links_prospect_and_latest_attempt(conn):
    pid, aid = _prospect_with_attempt(conn)
    event_id = record_manual_reply(conn, pid, "sounds interesting — let's talk")
    row = conn.execute("SELECT * FROM dm_events WHERE id = ?", (event_id,)).fetchone()
    assert row["x_dm_event_id"].startswith("manual-")
    assert row["prospect_id"] == pid
    assert row["outreach_attempt_id"] == aid
    assert row["event_type"] == "MessageCreate"
    assert row["sender_x_user_id"] == "100"


def test_manual_reply_without_any_attempt_still_links_prospect(conn):
    pid = store.upsert_prospect(conn, Prospect(x_user_id="200", username="solo", source="seed"))
    event_id = record_manual_reply(conn, pid)
    row = conn.execute("SELECT * FROM dm_events WHERE id = ?", (event_id,)).fetchone()
    assert row["prospect_id"] == pid and row["outreach_attempt_id"] is None


def test_manual_reply_unknown_prospect_raises(conn):
    with pytest.raises(ValueError):
        record_manual_reply(conn, 4242)


# --- automated path (SHOULD tier, exercised against the fake client) ---------

def test_ingest_links_inbound_reply_and_is_idempotent(conn):
    pid, aid = _prospect_with_attempt(conn)
    client = FakeXClient(dm_events=[
        DMEventPayload(id="evt1", event_type="MessageCreate", conversation_id="c1",
                       sender_id="100", text="interested!", created_at="2026-11-12T00:00:00Z"),
        DMEventPayload(id="evt2", event_type="ParticipantsJoin", conversation_id="c1",
                       sender_id="100"),
    ])
    assert ingest_reply_events(conn, client) == 1  # only MessageCreate stored
    assert ingest_reply_events(conn, client) == 0  # same API event id -> no duplicates
    replies = latest_replies_for_prospect(conn, pid)
    assert len(replies) == 1
    assert replies[0]["outreach_attempt_id"] == aid
    assert replies[0]["text"] == "interested!"


def test_ingest_skips_senders_that_are_not_known_prospects(conn):
    _prospect_with_attempt(conn)
    client = FakeXClient(dm_events=[
        DMEventPayload(id="evt9", event_type="MessageCreate", sender_id="99999",
                       text="from a stranger"),
    ])
    assert ingest_reply_events(conn, client) == 0
    assert conn.execute("SELECT COUNT(*) FROM dm_events").fetchone()[0] == 0


def test_ingest_with_unavailable_endpoint_raises_explicitly(conn):
    _prospect_with_attempt(conn)
    client = FakeXClient(unavailable={"get_dm_events"})
    with pytest.raises(EndpointUnavailable):
        ingest_reply_events(conn, client)  # workflow translates this to manual-mode guidance
