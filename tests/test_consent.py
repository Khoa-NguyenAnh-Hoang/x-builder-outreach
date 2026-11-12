import sqlite3

import pytest

from src.config import Settings
from src.db import connect, init_db
from src.db import store
from src.models import Prospect
from src.services.consent import (
    ConsentState,
    OptedOutLockedError,
    consume_approval,
    evaluate_send_eligibility,
    get_consent_state,
    mark_opt_out,
    record_consent,
    verify_consent,
)


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


@pytest.fixture
def settings():
    return Settings(_env_file=None, test_recipient_allowlist="100")


def _prospect(conn, x_user_id="100") -> int:
    return store.upsert_prospect(conn, Prospect(
        x_user_id=x_user_id, username="robo", source="seed"))


def _approved_draft(conn, prospect_id: int) -> int:
    did = store.create_draft(conn, _draft_model(prospect_id))
    store.set_draft_status(conn, did, "approved", approved_at=store.now_iso())
    return did


def _draft_model(prospect_id: int):
    from src.models import Draft
    return Draft(prospect_id=prospect_id, text="Hi!", evidence_refs=[], generator="template")


def _allow(**over) -> Settings:
    fields = dict(test_recipient_allowlist="100")
    fields.update(over)
    return Settings(_env_file=None, **fields)


# --- consent state machine --------------------------------------------------

def test_consent_starts_none_and_progresses(conn):
    pid = _prospect(conn)
    assert get_consent_state(conn, pid) == ConsentState(
        opted_out=False, consent="none", consent_source=None, approved_draft_id=None)
    record_consent(conn, pid, source="their public post", evidence_url="https://x.com/robo/1")
    assert get_consent_state(conn, pid).consent == "pending"
    verify_consent(conn, pid, verified_by="operator")
    state = get_consent_state(conn, pid)
    assert state.consent == "verified"


def test_opt_out_is_immediate_and_locks_consent_writes(conn):
    pid = _prospect(conn)
    mark_opt_out(conn, pid)
    assert get_consent_state(conn, pid).opted_out is True
    with pytest.raises(OptedOutLockedError, match="I2"):
        record_consent(conn, pid, source="oops")
    with pytest.raises(OptedOutLockedError):
        verify_consent(conn, pid, verified_by="operator")
    assert get_consent_state(conn, pid).opted_out is True  # suppression survives


def test_opt_out_keeps_existing_consent_fields(conn):
    pid = _prospect(conn)
    record_consent(conn, pid, source="post", evidence_url="https://x.com/robo/1")
    mark_opt_out(conn, pid)
    row = conn.execute("SELECT * FROM consent_records").fetchone()
    assert row["source"] == "post" and row["opted_out_at"] is not None


# --- eligibility gate (design doc A3) ----------------------------------------

def test_send_denied_without_per_message_approval(conn, settings):
    pid = _prospect(conn)
    d = evaluate_send_eligibility(conn, pid, "operator_approved", settings)
    assert not d.allowed and d.reason == "per-message operator approval"
    check = next(c for c in d.checks if c.invariant == "I1")
    assert not check.passed


def test_send_allowed_after_approval_in_operator_mode(conn, settings):
    pid = _prospect(conn)
    _approved_draft(conn, pid)
    d = evaluate_send_eligibility(conn, pid, "operator_approved", settings)
    assert d.allowed and d.reason == "all checks passed"
    assert all(c.passed for c in d.checks)


def test_opted_out_beats_everything(conn, settings):
    pid = _prospect(conn)
    _approved_draft(conn, pid)
    mark_opt_out(conn, pid)
    d = evaluate_send_eligibility(conn, pid, "operator_approved", settings)
    assert not d.allowed and d.reason == "opt-out suppression"  # I2 first, always


def test_dev_test_mode_requires_allowlist(conn):
    pid = _prospect(conn)
    _approved_draft(conn, pid)
    d = evaluate_send_eligibility(conn, pid, "dev_test", _allow(test_recipient_allowlist=""))
    assert not d.allowed and d.reason == "test-recipient allowlist"
    d2 = evaluate_send_eligibility(conn, pid, "dev_test", _allow())
    assert d2.allowed


def test_automated_batch_requires_verified_opt_in(conn, settings):
    pid = _prospect(conn)
    _approved_draft(conn, pid)
    d = evaluate_send_eligibility(conn, pid, "automated_batch", settings)
    assert not d.allowed and d.reason == "verified recipient opt-in"
    record_consent(conn, pid, source="they asked for a DM")
    assert not evaluate_send_eligibility(conn, pid, "automated_batch", settings).allowed  # pending
    verify_consent(conn, pid, verified_by="operator")
    assert evaluate_send_eligibility(conn, pid, "automated_batch", settings).allowed


def test_duplicate_active_attempt_blocks_send(conn, settings):
    pid = _prospect(conn)
    did = _approved_draft(conn, pid)
    store.create_send_intent(conn, pid, did, "operator_approved")
    d = evaluate_send_eligibility(conn, pid, "operator_approved", settings)
    assert not d.allowed and d.reason == "no active outreach attempt"


def test_volume_caps_block_at_limit(conn):
    pid = _prospect(conn)
    _approved_draft(conn, pid)
    strict = Settings(_env_file=None, send_cap_15min=2, send_cap_24h=40)
    # caps are account-level (all sends go out through one X account), so
    # attempts to *other* recipients also fill the window
    for i in range(2):
        other_id = store.upsert_prospect(conn, Prospect(
            x_user_id=f"90{i}", username=f"other{i}", source="seed"))
        other_draft = store.create_draft(conn, _draft_model(other_id))
        store.create_send_intent(conn, other_id, other_draft, "dev_test")
    d = evaluate_send_eligibility(conn, pid, "operator_approved", strict)
    assert not d.allowed and d.reason == "volume caps"
    check = next(c for c in d.checks if c.invariant == "I5")
    assert "2/2" in check.detail


def test_unavailable_api_blocks_send(conn, settings):
    pid = _prospect(conn)
    _approved_draft(conn, pid)
    d = evaluate_send_eligibility(conn, pid, "operator_approved", settings, api_available=False)
    assert not d.allowed and d.reason == "X API available"


def test_invalid_mode_rejected(conn, settings):
    with pytest.raises(ValueError):
        evaluate_send_eligibility(conn, 1, "yolo", settings)


# --- approval consumption (I1: one send per approval) -------------------------

def test_consume_approval_requires_reapproval(conn, settings):
    pid = _prospect(conn)
    _approved_draft(conn, pid)
    assert evaluate_send_eligibility(conn, pid, "operator_approved", settings).allowed
    consumed = consume_approval(conn, pid)
    assert consumed == 1
    assert get_consent_state(conn, pid).approved_draft_id is None
    assert not evaluate_send_eligibility(conn, pid, "operator_approved", settings).allowed
