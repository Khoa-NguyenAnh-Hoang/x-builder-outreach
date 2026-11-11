import json
import sqlite3

import pytest

from src.db import connect, init_db
from src.db import store
from src.models import ConsentRecord, DMEvent, Draft, Evidence, Prospect, Qualification


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def _prospect(**overrides) -> Prospect:
    fields = dict(x_user_id="12345", username="builder", source="seed")
    fields.update(overrides)
    return Prospect(**fields)


def _draft(conn, prospect_id: int) -> int:
    return store.create_draft(
        conn,
        Draft(prospect_id=prospect_id, text="hi",
              evidence_refs=[{"claim": "builds robots", "evidence_id": 1}],
              generator="template"),
    )


# --- initialization -------------------------------------------------------

def test_init_db_is_repeatable_and_never_drops_data(conn):
    store.upsert_prospect(conn, _prospect())
    init_db(conn)  # second call at same version is a no-op
    (version,) = conn.execute("PRAGMA user_version").fetchone()
    assert version == 1
    assert store.get_prospect_by_x_user_id(conn, "12345") is not None


def test_init_db_rejects_newer_schema():
    c = connect(":memory:")
    c.execute("PRAGMA user_version = 999")
    with pytest.raises(RuntimeError, match="newer"):
        init_db(c)


# --- prospects ------------------------------------------------------------

def test_prospect_upsert_update_and_read(conn):
    pid = store.upsert_prospect(conn, _prospect(bio="old bio"))
    row = store.get_prospect_by_x_user_id(conn, "12345")
    first_seen = row["first_seen_at"]
    assert row["bio"] == "old bio"

    store.upsert_prospect(conn, _prospect(bio="new bio", username="builder2"))
    row = store.get_prospect_by_x_user_id(conn, "12345")
    assert row["bio"] == "new bio"
    assert row["username"] == "builder2"
    assert row["first_seen_at"] == first_seen  # preserved across updates
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 1


def test_duplicate_prospect_x_user_id_stays_single_row(conn):
    store.upsert_prospect(conn, _prospect())
    store.upsert_prospect(conn, _prospect())
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 1


# --- foreign keys ---------------------------------------------------------

def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO evidence (prospect_id, url, source_type, captured_at)"
            " VALUES (99999, 'http://x', 'post', 'now')"
        )


# --- evidence / qualification / consent -----------------------------------

def test_evidence_dedup_by_url_updates_in_place(conn):
    pid = store.upsert_prospect(conn, _prospect())
    e1 = store.upsert_evidence(conn, Evidence(prospect_id=pid, url="http://x/1",
                                              source_type="post", text="v1"))
    store.upsert_evidence(conn, Evidence(prospect_id=pid, url="http://x/1",
                                         source_type="post", text="v2"))
    rows = conn.execute("SELECT * FROM evidence").fetchall()
    assert len(rows) == 1 and rows[0]["text"] == "v2" and rows[0]["id"] == e1


def test_qualification_upsert_keeps_single_row(conn):
    pid = store.upsert_prospect(conn, _prospect())
    store.save_qualification(conn, Qualification(
        prospect_id=pid, score=0.5, components={"relevance": 0.5},
        reasons=["posts about AI"], confidence="medium"))
    store.save_qualification(conn, Qualification(
        prospect_id=pid, score=0.9, components={"relevance": 0.9},
        reasons=["posts about robotics"], confidence="high"))
    row = conn.execute("SELECT * FROM qualification_results").fetchone()
    assert row["score"] == 0.9
    assert json.loads(row["reasons"]) == ["posts about robotics"]


def test_consent_opt_out_state(conn):
    pid = store.upsert_prospect(conn, _prospect())
    assert store.is_opted_out(conn, pid) is False
    store.upsert_consent(conn, ConsentRecord(
        prospect_id=pid, source="operator", scope="manual", opted_out_at="2026-11-11T00:00:00Z"))
    assert store.is_opted_out(conn, pid) is True


# --- outreach attempts (invariant I7) --------------------------------------

def test_duplicate_active_send_intent_rejected_then_allowed_after_resolve(conn):
    pid = store.upsert_prospect(conn, _prospect())
    did = _draft(conn, pid)

    a1 = store.create_send_intent(conn, pid, did, "operator_approved")
    with pytest.raises(sqlite3.IntegrityError):  # intent/sent/unknown block a second attempt
        store.create_send_intent(conn, pid, did, "operator_approved")

    store.resolve_send_attempt(conn, a1, "failed")  # terminal -> no longer active
    a2 = store.create_send_intent(conn, pid, did, "operator_approved")
    assert a2 != a1


def test_sent_attempt_blocks_new_intent(conn):
    pid = store.upsert_prospect(conn, _prospect())
    did = _draft(conn, pid)
    a1 = store.create_send_intent(conn, pid, did, "dev_test")
    store.resolve_send_attempt(conn, a1, "sent", x_conversation_id="c1", x_event_id="e1")
    with pytest.raises(sqlite3.IntegrityError):
        store.create_send_intent(conn, pid, did, "dev_test")


def test_denied_send_does_not_block_later_sends(conn):
    pid = store.upsert_prospect(conn, _prospect())
    did = _draft(conn, pid)
    store.record_denied_send(conn, pid, did, "operator_approved", "opted_out")
    assert store.has_active_attempt(conn, pid) is False
    store.create_send_intent(conn, pid, did, "operator_approved")  # no raise
    assert store.has_active_attempt(conn, pid) is True


def test_attempt_status_is_constrained(conn):
    pid = store.upsert_prospect(conn, _prospect())
    did = _draft(conn, pid)
    aid = store.create_send_intent(conn, pid, did, "dev_test")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE outreach_attempts SET status = 'bogus' WHERE id = ?", (aid,))


def test_send_intent_requires_existing_draft(conn):
    pid = store.upsert_prospect(conn, _prospect())
    with pytest.raises(sqlite3.IntegrityError):
        store.create_send_intent(conn, pid, 99999, "dev_test")


# --- dm events -------------------------------------------------------------

def test_dm_event_ingestion_is_idempotent(conn):
    pid = store.upsert_prospect(conn, _prospect())
    ev = DMEvent(x_dm_event_id="evt1", prospect_id=pid, event_type="MessageCreate",
                 sender_x_user_id="12345", text="thanks!", occurred_at="2026-11-11T00:00:00Z")
    assert store.insert_dm_event(conn, ev) is True
    assert store.insert_dm_event(conn, ev) is False  # same API event id -> no duplicate
    assert conn.execute("SELECT COUNT(*) FROM dm_events").fetchone()[0] == 1


def test_draft_status_transitions(conn):
    pid = store.upsert_prospect(conn, _prospect())
    did = _draft(conn, pid)
    store.set_draft_status(conn, did, "approved", approved_at="2026-11-11T00:00:00Z")
    row = conn.execute("SELECT status, approved_at FROM drafts WHERE id = ?", (did,)).fetchone()
    assert row["status"] == "approved" and row["approved_at"] is not None
