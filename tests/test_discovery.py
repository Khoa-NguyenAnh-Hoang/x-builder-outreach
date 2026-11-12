import sqlite3

import pytest
from pydantic import ValidationError

from src.db import connect, init_db
from src.integrations.fake_x_client import FakeXClient
from src.integrations.x_client import Page, Post, Profile, RateLimitError
from src.services.discovery import MAX_PAGES, DiscoveryQuery, run_discovery


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def _client(**overrides) -> FakeXClient:
    kwargs = dict(
        profiles=[
            Profile(id="100", username="robo", name="Robo", description="building humanoid robots", follower_count=120),
            Profile(id="200", username="llmguy", name="L", description="LLM tooling"),
        ],
        posts=[
            Post(id="p1", author_id="100", text="shipped our perception stack", created_at="2026-11-10T00:00:00Z"),
            Post(id="p2", author_id="200", text="new eval harness", created_at="2026-11-09T00:00:00Z"),
        ],
    )
    kwargs.update(overrides)
    return FakeXClient(**kwargs)


def test_query_page_bound_is_enforced():
    with pytest.raises(ValidationError):
        DiscoveryQuery(queries=["x"], max_pages=MAX_PAGES + 1)


def test_seed_discovery_creates_stable_candidates(conn):
    run = run_discovery(conn, _client(), DiscoveryQuery(seeds=["robo"]))
    row = conn.execute("SELECT * FROM prospects").fetchone()
    assert row["x_user_id"] == "100" and row["source"] == "seed"
    assert run.candidates_upserted == 1 and run.new_candidates == 1


def test_unknown_seed_is_skipped_with_warning(conn):
    run = run_discovery(conn, _client(), DiscoveryQuery(seeds=["ghost_user"]))
    assert run.candidates_upserted == 0
    assert any("ghost_user" in w for w in run.warnings)


def test_topic_query_links_posts_to_author_candidates(conn):
    run = run_discovery(conn, _client(), DiscoveryQuery(queries=["robotics founders"]))
    assert run.candidates_upserted == 2
    assert set(run.posts_by_author) == {"100", "200"}
    client = _client()
    run_discovery(conn, client, DiscoveryQuery(queries=["robotics founders"]))
    assert client.get_users_calls and set(client.get_users_calls[0]) == {"100", "200"}


def test_repeated_discovery_updates_instead_of_duplicating(conn):
    run_discovery(conn, _client(), DiscoveryQuery(seeds=["robo"]))
    run2 = run_discovery(conn, _client(profiles=[
        Profile(id="100", username="robo", name="Robo", description="updated bio"),
    ]), DiscoveryQuery(seeds=["robo"]))
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 1
    assert run2.new_candidates == 0 and run2.candidates_upserted == 1
    row = conn.execute("SELECT bio FROM prospects").fetchone()
    assert row["bio"] == "updated bio"


def test_pagination_is_bounded(conn):
    pages = [
        Page(data=[Post(id="p1", author_id="100", text="a")], next_token="t1"),
        Page(data=[Post(id="p2", author_id="200", text="b")], next_token="t2"),
        Page(data=[Post(id="p3", author_id="300", text="c")], next_token=None),
    ]
    client = _client(search_pages=list(pages))
    run = run_discovery(conn, client, DiscoveryQuery(queries=["ai"], max_pages=2))
    assert len(client.search_calls) == 2  # stopped at the bound despite next_token="t2"
    # page 3's author never became a candidate
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 2


def test_pagination_stops_when_api_says_done(conn):
    pages = [
        Page(data=[Post(id="p1", author_id="100", text="a")], next_token=None),
        Page(data=[Post(id="p2", author_id="200", text="b")], next_token=None),
    ]
    client = _client(search_pages=list(pages))
    run_discovery(conn, client, DiscoveryQuery(queries=["ai"], max_pages=3))
    assert len(client.search_calls) == 1  # respected the API's no-more-pages signal


def test_rate_limit_keeps_partial_results_and_warns(conn):
    client = _client()
    client.fail_next("search_recent_posts", RateLimitError("slow down", reset_seconds=900))
    run = run_discovery(conn, client, DiscoveryQuery(queries=["robotics"]))
    assert run.candidates_upserted == 0  # nothing collected before the hit
    assert any("rate limited" in w and "robotics" in w for w in run.warnings)
