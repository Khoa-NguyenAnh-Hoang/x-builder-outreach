import json

import pytest

from src.db import connect, init_db
from src.integrations.fake_x_client import FakeXClient
from src.integrations.x_client import Post, Profile
from src.services.discovery import DiscoveryQuery
from src.services.pipeline import discover_and_qualify
from src.services.qualification import WEIGHTS, qualify


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def _profile(**over) -> Profile:
    fields = dict(id="100", username="robo", name="Robo",
                  description="Founder building humanoid robots. ex-PhD researcher")
    fields.update(over)
    return Profile(**fields)


def _post(**over) -> Post:
    fields = dict(id="p1", author_id="100", created_at="2026-11-10T00:00:00Z",
                  text="released our new ML perception model, open source on GitHub")
    fields.update(over)
    return Post(**fields)


# --- component behavior (pure function, reproducible) -----------------------

def test_relevant_builder_scores_high_with_cited_reasons():
    q = qualify(1, _profile(), [_post()])
    assert q.components["relevance"] == 1.0
    assert q.components["role"] == 1.0
    assert q.components["contribution"] == 1.0
    assert q.confidence == "medium"  # profile + 1 post
    assert any("robot" in r for r in q.reasons)          # robotics terms cited
    assert any("founder" in r or "researcher" in r for r in q.reasons)
    assert any("github" in r for r in q.reasons)
    expected = round(sum(WEIGHTS[k] * q.components[k] for k in WEIGHTS), 4)
    assert q.score == expected  # reproducible from exposed weights


def test_irrelevant_profile_scores_zero_relevance():
    profile = Profile(id="300", username="snaps", name="S", description="landscape photographer")
    post = Post(id="p9", author_id="300", text="sunset shots from the coast", created_at="2026-11-10T00:00:00Z")
    q = qualify(2, profile, [post])
    assert q.components["relevance"] == 0.0
    assert any("no AI/robotics signals" in r for r in q.reasons)


def test_stale_evidence_lowers_freshness_component():
    q = qualify(3, _profile(), [_post(created_at="2026-05-01T00:00:00Z")])  # >90d old
    assert q.components["freshness"] == 0.1
    assert any("stale" in r for r in q.reasons)


def test_word_boundary_matching_no_false_positives():
    # 'ai' must not match inside 'email'/'said'; 'ml' must not match 'html'
    profile = Profile(id="400", username="x", name="X", description="email newsletters and html sites")
    q = qualify(4, profile, [])
    assert q.components["relevance"] == 0.0


def test_no_evidence_is_reported_not_inferred():
    q = qualify(5, None, [])
    assert q.score == 0.0
    assert all(v == 0.0 for v in q.components.values())
    assert q.confidence == "low"
    assert any("insufficient evidence" in r and "not by inference" in r for r in q.reasons)


def test_profile_only_evidence_limits_confidence():
    q = qualify(6, _profile(), [])
    assert q.confidence == "low"
    assert any("profile-only evidence" in r for r in q.reasons)
    assert q.components["freshness"] == 0.0  # unknown, not inferred


def test_same_evidence_same_score():
    a = qualify(7, _profile(), [_post(), _post(id="p2", text="robot demo at the lab")])
    b = qualify(7, _profile(), [_post(), _post(id="p2", text="robot demo at the lab")])
    assert a == b


# --- persisted pipeline (T08+T09 glue) --------------------------------------

def test_pipeline_persists_candidates_evidence_and_qualification(conn):
    client = FakeXClient(
        profiles=[_profile()],
        posts=[_post()],
    )
    result = discover_and_qualify(
        conn, client,
        # seeds create the candidate; a topic query is what attaches post evidence
        DiscoveryQuery(seeds=["robo"], queries=["robotics founders"]),
    )

    assert "100" in result.qualifications
    qual_row = conn.execute("SELECT * FROM qualification_results").fetchone()
    assert qual_row is not None
    assert json.loads(qual_row["components"])["relevance"] == 1.0

    evidence = conn.execute("SELECT url, source_type FROM evidence ORDER BY source_type").fetchall()
    assert [(r["source_type"], r["url"]) for r in evidence] == [
        ("post", "https://x.com/robo/status/p1"),
        ("profile", "https://x.com/robo"),
    ]  # every qualified candidate has inspectable evidence with source URLs


def test_pipeline_rerun_refreshes_evidence_without_duplicates(conn):
    client = FakeXClient(profiles=[_profile()], posts=[_post()])
    query = DiscoveryQuery(seeds=["robo"], queries=["robotics founders"])
    discover_and_qualify(conn, client, query)
    discover_and_qualify(conn, client, query)
    assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 2  # same URLs refreshed
    assert conn.execute("SELECT COUNT(*) FROM qualification_results").fetchone()[0] == 1
