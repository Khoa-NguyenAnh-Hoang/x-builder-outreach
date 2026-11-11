import pytest

from src.integrations.fake_x_client import FakeXClient
from src.integrations.x_client import (
    AuthenticationError,
    DMEventPayload,
    EndpointUnavailable,
    MalformedResponseError,
    Page,
    Post,
    Profile,
    RateLimitError,
    RequestTimeout,
    SendResult,
    XClient,
    XClientError,
)


def _fake(**overrides) -> FakeXClient:
    kwargs = dict(
        posts=[
            Post(id="p1", author_id="100", text="building a robot arm"),
            Post(id="p2", author_id="200", text="LLM eval tooling"),
        ],
        profiles=[
            Profile(id="100", username="robo", name="Robo", follower_count=120),
            Profile(id="200", username="llmguy", name="L"),
        ],
        dm_events=[
            DMEventPayload(id="e1", event_type="MessageCreate", conversation_id="c1",
                           sender_id="100", text="inbound"),
        ],
    )
    kwargs.update(overrides)
    return FakeXClient(**kwargs)


# --- boundary contract -----------------------------------------------------

def test_fake_satisfies_the_xclient_protocol():
    assert isinstance(_fake(), XClient)


def test_all_error_types_share_the_boundary_base():
    for exc in (AuthenticationError, RateLimitError, MalformedResponseError,
                RequestTimeout, EndpointUnavailable):
        assert issubclass(exc, XClientError)


# --- success paths ---------------------------------------------------------

def test_search_returns_canned_posts_and_records_the_call():
    fake = _fake()
    page = fake.search_recent_posts("robotics", max_results=1)
    assert isinstance(page, Page)
    assert [p.id for p in page.data] == ["p1"]
    assert page.next_token is None
    assert fake.search_calls == [{"query": "robotics", "max_results": 1, "next_token": None}]


def test_get_users_returns_only_requested_ids():
    fake = _fake()
    got = fake.get_users(["200"])
    assert [p.username for p in got] == ["llmguy"]
    assert fake.get_users_calls == [["200"]]


def test_send_dm_returns_send_result_with_fake_ids():
    fake = _fake()
    result = fake.send_dm("100", "hello")
    assert isinstance(result, SendResult)
    assert result.dm_conversation_id.startswith("fake-")
    assert result.dm_event_id.startswith("fake-")
    assert fake.send_calls == [("100", "hello")]


def test_get_dm_events_filters_by_participant_or_conversation():
    fake = _fake()
    assert fake.get_dm_events(participant_id="100")[0].id == "e1"
    assert fake.get_dm_events(conversation_id="c1")[0].id == "e1"
    assert fake.get_dm_events(participant_id="999") == []
    assert fake.get_dm_events()[0].id == "e1"  # unfiltered returns everything


# --- scripted failures: success, auth, rate limit, malformed, timeout -------

def test_injected_auth_failure_is_one_shot_then_recovers():
    fake = _fake()
    fake.fail_next("search_recent_posts", AuthenticationError("invalid token"))
    with pytest.raises(AuthenticationError):
        fake.search_recent_posts("robotics")
    assert fake.search_recent_posts("robotics").data[0].id == "p1"  # recovered


def test_rate_limit_error_carries_reset_window():
    fake = _fake()
    fake.fail_next("send_dm", RateLimitError("slow down", reset_seconds=900))
    with pytest.raises(RateLimitError) as err:
        fake.send_dm("100", "hi")
    assert err.value.reset_seconds == 900


def test_malformed_response_error_is_injectable():
    fake = _fake()
    fake.fail_next("get_users", MalformedResponseError("missing required field"))
    with pytest.raises(MalformedResponseError):
        fake.get_users(["100"])


def test_timeout_error_is_injectable():
    fake = _fake()
    fake.fail_next("get_dm_events", RequestTimeout("network timeout"))
    with pytest.raises(RequestTimeout):
        fake.get_dm_events()


# --- unavailable endpoints never simulate success --------------------------

def test_unavailable_endpoint_fails_explicitly_others_still_work():
    fake = _fake(unavailable={"send_dm"})
    with pytest.raises(EndpointUnavailable, match="not entitled"):
        fake.send_dm("100", "hi")
    assert fake.send_calls == [("100", "hi")]  # attempt was recorded, then rejected
    assert fake.search_recent_posts("robotics").data  # other endpoints unaffected


def test_unavailable_endpoint_raises_every_time():
    fake = _fake(unavailable={"get_dm_events"})
    for _ in range(2):
        with pytest.raises(EndpointUnavailable):
            fake.get_dm_events()
