import pytest

from src.config import Settings
from src.db import connect, init_db
from src.db import store
from src.integrations.fake_x_client import FakeXClient
from src.integrations.x_client import AuthenticationError, Post, Profile
from src.services.drafting import NoGroundedEvidenceError
from src.ui import workflows
from src.ui.fixtures import offline_client


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def _client(**over) -> FakeXClient:
    kwargs = dict(
        profiles=[
            Profile(id="100", username="robo", name="Robo",
                    description="Founder building humanoid robots. ex-PhD", follower_count=1200),
        ],
        posts=[Post(id="p1", author_id="100", created_at="2026-11-10T00:00:00Z",
                    text="shipped our perception stack, open source on github")],
    )
    kwargs.update(over)
    return FakeXClient(**kwargs)


# --- discovery workflow (terminal-free operator capability, T11 acceptance) ---

def test_discovery_workflow_runs_without_a_terminal(conn):
    result = workflows.run_discovery_workflow(
        conn, _client(), "robo", "robotics founders")
    assert not isinstance(result, workflows.WorkflowError)
    assert result.run.new_candidates == 1  # seed + query both hit the same candidate
    candidates = workflows.load_candidates(conn)
    assert len(candidates) == 1 and candidates[0]["username"] == "robo"


def test_discovery_workflow_rejects_empty_input(conn):
    err = workflows.run_discovery_workflow(conn, _client(), "  ", "")
    assert isinstance(err, workflows.WorkflowError)
    assert "at least one" in err.message


def test_discovery_workflow_rejects_out_of_range_pages(conn):
    err = workflows.run_discovery_workflow(conn, _client(), "robo", "", max_pages=99)
    assert isinstance(err, workflows.WorkflowError)
    assert "invalid discovery input" in err.message


def test_discovery_workflow_translates_auth_failure_into_guidance(conn):
    client = _client()
    client.fail_next("get_users_by_usernames", AuthenticationError("bad key"))
    err = workflows.run_discovery_workflow(conn, client, "robo", "")
    assert isinstance(err, workflows.WorkflowError)
    assert "docs/x-api-feasibility.md" in err.message


# --- candidate listing / detail (inspect evidence, populated + empty states) --

def test_load_candidates_empty_state(conn):
    assert workflows.load_candidates(conn) == []


def test_load_candidates_ordered_best_first_with_reasons(conn):
    workflows.run_discovery_workflow(conn, _client(), "robo", "robotics founders")
    from src.models import Prospect
    store.upsert_prospect(conn, Prospect(x_user_id="500", username="baker", source="seed"))
    candidates = workflows.load_candidates(conn)
    assert candidates[0]["username"] == "robo"           # qualified ranks above unscored
    assert candidates[0]["score"] is not None
    assert candidates[0]["reasons"]                       # inspectable
    assert candidates[0]["evidence_count"] == 2


def test_load_candidate_detail_includes_evidence_and_consent(conn):
    workflows.run_discovery_workflow(conn, _client(), "robo", "robotics founders")
    pid = workflows.load_candidates(conn)[0]["id"]
    detail = workflows.load_candidate_detail(conn, pid)
    assert len(detail["evidence"]) == 2
    assert {e["source_type"] for e in detail["evidence"]} == {"profile", "post"}
    assert detail["consent_state"].consent == "none"
    assert isinstance(detail["consent_state"], workflows.ConsentState)


def test_load_candidate_detail_unknown_id(conn):
    assert isinstance(workflows.load_candidate_detail(conn, 4242), workflows.WorkflowError)


# --- draft workflow -----------------------------------------------------------

def test_draft_workflow_generates_and_records(conn):
    workflows.run_discovery_workflow(conn, _client(), "robo", "")
    pid = workflows.load_candidates(conn)[0]["id"]
    draft = workflows.draft_for_candidate(conn, pid)
    assert not isinstance(draft, workflows.WorkflowError)
    assert draft.generator == "template"
    rows = conn.execute("SELECT status FROM drafts").fetchall()
    assert rows[0]["status"] == "draft"  # unapproved until the operator approves


def test_draft_workflow_reports_missing_evidence(conn):
    from src.models import Prospect
    pid = store.upsert_prospect(conn, Prospect(x_user_id="777", username="bare", source="seed"))
    err = workflows.draft_for_candidate(conn, pid)
    assert isinstance(err, workflows.WorkflowError)
    assert "evidence" in err.message


def test_approve_then_eligibility_allows_in_operator_mode(conn):
    settings = Settings(_env_file=None, test_recipient_allowlist="100")
    workflows.run_discovery_workflow(conn, _client(), "robo", "")
    pid = workflows.load_candidates(conn)[0]["id"]
    draft = workflows.draft_for_candidate(conn, pid)

    before = workflows.check_send_eligibility(conn, pid, "operator_approved", settings)
    assert not before.allowed and before.reason == "per-message operator approval"

    workflows.approve_draft(conn, draft.draft_id)
    after = workflows.check_send_eligibility(conn, pid, "operator_approved", settings)
    assert after.allowed

    workflows.mark_opt_out(conn, pid)
    suppressed = workflows.check_send_eligibility(conn, pid, "operator_approved", settings)
    assert not suppressed.allowed and suppressed.reason == "opt-out suppression"
