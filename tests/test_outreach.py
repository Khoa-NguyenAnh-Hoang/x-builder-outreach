"""T13 — the send chain on fakes. Every gate rule keeps its promise: denied means
no API call, unknown means never retried, failed means definitively not sent."""

import pytest

from src.config import Settings
from src.db import connect, init_db, store
from src.integrations.fake_x_client import FakeXClient
from src.integrations.x_client import (
    AuthenticationError,
    MalformedResponseError,
    RequestTimeout,
)
from src.models import Draft, Prospect
from src.services.consent import mark_opt_out
from src.services.outreach import send_approved_draft


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def _settings(**over) -> Settings:
    fields = dict(test_recipient_allowlist="100")
    fields.update(over)
    return Settings(_env_file=None, **fields)


def _approved(conn, x_user_id="100", username="robo", text="Hi! Evidence says you build robots.") -> int:
    pid = store.upsert_prospect(conn, Prospect(
        x_user_id=x_user_id, username=username, source="seed"))
    did = store.create_draft(conn, Draft(
        prospect_id=pid, text=text, evidence_refs=[], generator="template"))
    store.set_draft_status(conn, did, "approved", approved_at=store.now_iso())
    return pid


def _fake(**over) -> FakeXClient:
    return FakeXClient(**over)


# --- the gate rules hold inside the send chain --------------------------------

def test_unapproved_draft_denied_and_no_api_call(conn):
    client = _fake()
    from src.models import Prospect
    pid = store.upsert_prospect(conn, Prospect(x_user_id="100", username="robo", source="seed"))
    store.create_draft(conn, Draft(prospect_id=pid, text="Hi!", evidence_refs=[], generator="template"))

    outcome = send_approved_draft(conn, client, pid, _settings(), "operator_approved")

    assert outcome.status == "denied"
    assert outcome.deny_reason == "per-message operator approval"
    assert client.send_calls == []                       # API never touched
    row = conn.execute("SELECT status, deny_reason FROM outreach_attempts").fetchone()
    assert row["status"] == "failed" and row["deny_reason"] == "per-message operator approval"


def test_opted_out_recipient_denied_before_anything_else(conn):
    client = _fake()
    pid = _approved(conn)
    mark_opt_out(conn, pid)

    outcome = send_approved_draft(conn, client, pid, _settings(), "operator_approved")

    assert outcome.status == "denied"
    assert outcome.deny_reason == "opt-out suppression"  # I2 outranks the approved draft
    assert client.send_calls == []


def test_dev_test_mode_requires_allowlist(conn):
    client = _fake()
    pid = _approved(conn)
    outcome = send_approved_draft(conn, client, pid, _settings(test_recipient_allowlist=""), "dev_test")
    assert outcome.status == "denied" and outcome.deny_reason == "test-recipient allowlist"
    assert client.send_calls == []


# --- the happy path ------------------------------------------------------------

def test_approved_send_sends_resolves_and_consumes_approval(conn):
    client = _fake()
    pid = _approved(conn)
    draft = conn.execute("SELECT id, text FROM drafts").fetchone()

    outcome = send_approved_draft(conn, client, pid, _settings(), "operator_approved")

    assert outcome.status == "sent"
    assert outcome.message_id.startswith("fake-")
    assert client.send_calls == [("100", draft["text"])]
    attempt = conn.execute("SELECT * FROM outreach_attempts").fetchone()
    assert attempt["status"] == "sent" and attempt["x_event_id"] == outcome.message_id
    draft_after = conn.execute("SELECT status FROM drafts").fetchone()
    assert draft_after["status"] == "superseded"  # I1: approval consumed by one send

    second = send_approved_draft(conn, client, pid, _settings(), "operator_approved")
    assert second.status == "denied"   # reason is I1 (approval consumed) — policy order;
    assert len(client.send_calls) == 1  # the duplicate rule is the DB backstop (test_db.py)


# --- ambiguous vs definitive failures -------------------------------------------

def test_timeout_is_unknown_and_never_automatically_retried(conn):
    client = _fake()
    client.fail_next("send_dm", RequestTimeout("connection died"))
    pid = _approved(conn)

    outcome = send_approved_draft(conn, client, pid, _settings(), "operator_approved")

    assert outcome.status == "unknown"
    assert len(client.send_calls) == 1                    # exactly one attempt, no auto-retry
    attempt = conn.execute("SELECT status FROM outreach_attempts").fetchone()
    assert attempt["status"] == "unknown"
    # approval consumed: a message MAY exist — re-sending requires re-approval (I1)
    assert conn.execute("SELECT status FROM drafts").fetchone()["status"] == "superseded"


def test_malformed_response_is_unknown_because_delivery_is_possible(conn):
    client = _fake()
    client.fail_next("send_dm", MalformedResponseError("201 body unreadable"))
    pid = _approved(conn)

    outcome = send_approved_draft(conn, client, pid, _settings(), "operator_approved")
    assert outcome.status == "unknown"


def test_auth_error_is_failed_and_nothing_sent(conn):
    client = _fake()
    client.fail_next("send_dm", AuthenticationError("403: dm not entitled"))
    pid = _approved(conn)

    outcome = send_approved_draft(conn, client, pid, _settings(), "operator_approved")
    assert outcome.status == "failed"
    attempt = conn.execute("SELECT status, deny_reason FROM outreach_attempts").fetchone()
    assert attempt["status"] == "failed" and attempt["deny_reason"] is None  # attention-list item
    # approval retained: nothing was sent, so the operator may deliberately retry
    assert conn.execute("SELECT status FROM drafts").fetchone()["status"] == "approved"


def test_invalid_mode_surfaces_as_workflow_error(conn):
    with pytest.raises(ValueError):
        send_approved_draft(conn, _fake(), 1, _settings(), "yolo")
