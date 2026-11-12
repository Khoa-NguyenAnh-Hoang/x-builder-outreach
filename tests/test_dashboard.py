import pytest

from src.db import connect, init_db
from src.db import store
from src.models import Draft, Prospect
from src.services.conversations import record_manual_reply
from src.services.consent import mark_opt_out
from src.services.dashboard import dashboard_data


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def _prospect(conn, x_user_id, username) -> int:
    return store.upsert_prospect(conn, Prospect(
        x_user_id=x_user_id, username=username, source="seed"))


def _attempt(conn, prospect_id, status, deny_reason=None):
    did = store.create_draft(conn, Draft(
        prospect_id=prospect_id, text="Hi!", evidence_refs=[], generator="template"))
    aid = store.create_send_intent(conn, prospect_id, did, "operator_approved")
    if status != "intent":
        store.resolve_send_attempt(conn, aid, status, deny_reason=deny_reason)
    return aid


def test_empty_dashboard_shows_zeros_not_placeholders(conn):
    data = dashboard_data(conn)
    assert data.total_attempts == 0
    assert data.status_counts == {}
    assert data.replied_count == 0 and data.opted_out_count == 0
    assert data.attention == [] and data.recent_attempts == [] and data.replies == []
    assert data.tracking_mode == "manual"


def test_status_counts_match_database_queries(conn):
    a = _prospect(conn, "100", "robo")
    b = _prospect(conn, "200", "llm")
    c = _prospect(conn, "300", "x")
    d = _prospect(conn, "400", "ops")
    _attempt(conn, a, "sent")
    _attempt(conn, b, "failed", deny_reason="opted_out")   # policy denial
    _attempt(conn, c, "failed")                             # real failure
    _attempt(conn, d, "unknown")

    data = dashboard_data(conn)
    sql_counts = dict(conn.execute(
        "SELECT status, COUNT(*) FROM outreach_attempts GROUP BY status").fetchall())
    assert data.status_counts == sql_counts  # dashboard == database, literally
    assert data.status_counts == {"sent": 1, "failed": 2, "unknown": 1}
    assert data.total_attempts == 4


def test_attention_flags_unknown_and_real_failures_not_policy_denials(conn):
    a = _prospect(conn, "100", "robo")
    b = _prospect(conn, "200", "llm")
    c = _prospect(conn, "300", "x")
    _attempt(conn, a, "unknown")
    _attempt(conn, b, "failed", deny_reason="opted_out")
    _attempt(conn, c, "failed")

    data = dashboard_data(conn)
    attention = [(v.attempt_id, v.status) for v in data.attention]
    # unknown sorts first (most urgent), policy denials are NOT attention items
    assert len(attention) == 2
    assert attention[0][1] == "unknown"
    assert all(s == "failed" for _, s in attention[1:])
    assert a and b  # structure guard


def test_unknown_attempt_carries_ambiguity_warning_input(conn):
    a = _prospect(conn, "100", "robo")
    aid = _attempt(conn, a, "unknown")
    data = dashboard_data(conn)
    assert data.attention[0].attempt_id == aid
    assert data.attention[0].status == "unknown"  # UI renders the reconcile-before-retry warning


def test_replied_count_derived_from_dm_events(conn):
    a = _prospect(conn, "100", "robo")
    _attempt(conn, a, "sent")
    record_manual_reply(conn, a, "yes, happy to chat")
    data = dashboard_data(conn)
    assert data.replied_count == 1
    assert data.replies[0].source == "manual"
    assert data.replies[0].username == "robo"


def test_opted_out_count_and_suppression_visibility(conn):
    a = _prospect(conn, "100", "robo")
    _attempt(conn, a, "sent")
    mark_opt_out(conn, a)
    data = dashboard_data(conn)
    assert data.opted_out_count == 1
    # suppression enforcement itself is the T12 gate; dashboard reports the state
    assert conn.execute(
        "SELECT opted_out_at FROM consent_records WHERE prospect_id = ?", (a,)
    ).fetchone()[0] is not None


def test_tracking_mode_label_reflects_d4_state(conn):
    assert dashboard_data(conn).tracking_mode == "manual"
    assert dashboard_data(conn, automated_reply_tracking=True).tracking_mode == "api"
