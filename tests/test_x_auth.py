"""Unit tests for the OAuth 2.0 PKCE flow and the live client's error mapping —
all against httpx.MockTransport; the default suite never touches the network."""

import base64
import hashlib

import httpx
import pytest

from src.config import Settings
from src.integrations import x_auth
from src.integrations.x_client import (
    AuthenticationError,
    EndpointUnavailable,
    MalformedResponseError,
    OfficialXClient,
    Page,
    Profile,
    RateLimitError,
    RequestTimeout,
    SendResult,
)

# --- PKCE + authorize URL ----------------------------------------------------

def test_pkce_pair_is_valid_s256():
    verifier, challenge = x_auth.generate_pkce_pair()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected and "=" not in challenge


def test_authorize_url_carries_required_params():
    url = x_auth.build_authorize_url("cid", "http://127.0.0.1:8501/callback", "st", "chg")
    assert url.startswith("https://x.com/i/oauth2/authorize?")
    for frag in ("response_type=code", "client_id=cid", "state=st", "code_challenge=chg",
                 "code_challenge_method=s256", "dm.read", "offline.access"):
        assert frag in url


def test_extract_code_accepts_url_and_bare_code():
    url = "http://127.0.0.1:8501/callback?state=st&code=abc123"
    assert x_auth.extract_code(url) == "abc123"
    assert x_auth.extract_code("abc123") == "abc123"
    with pytest.raises(AuthenticationError, match="error"):
        x_auth.extract_code("http://127.0.0.1:8501/callback?error=access_denied")


def test_state_mismatch_rejected():
    with pytest.raises(AuthenticationError, match="state"):
        x_auth.validate_state("expected", "evil")
    x_auth.validate_state("expected", "expected")  # ok


# --- token storage + refresh -------------------------------------------------

def test_token_store_roundtrip(tmp_path):
    path = tmp_path / "tokens.json"
    x_auth.save_tokens({"access_token": "at", "refresh_token": "rt", "expires_in": 7200}, path)
    tokens = x_auth.load_tokens(path)
    assert tokens["access_token"] == "at" and tokens["refresh_token"] == "rt"
    assert tokens["expires_at"]


def test_fresh_tokens_are_not_refreshed(tmp_path):
    path = tmp_path / "tokens.json"
    x_auth.save_tokens({"access_token": "at", "refresh_token": "rt", "expires_in": 7200}, path)
    tokens = x_auth.ensure_fresh_tokens("cid", "secret", x_auth.load_tokens(path))
    assert tokens["access_token"] == "at"  # well inside the 60 s expiry margin


def test_expired_tokens_trigger_refresh(tmp_path):
    path = tmp_path / "tokens.json"
    x_auth.save_tokens({"access_token": "old", "refresh_token": "rt", "expires_in": 10}, path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/2/oauth2/token"
        body = request.content.decode()
        assert "grant_type=refresh_token" in body
        return httpx.Response(200, json={"access_token": "new", "refresh_token": "rt2",
                                         "expires_in": 7200, "scope": x_auth.SCOPES})

    tokens = x_auth.ensure_fresh_tokens("cid", "secret", transport=httpx.MockTransport(handler),
                                    path=path)
    assert tokens["access_token"] == "new"
    assert x_auth.load_tokens(path)["access_token"] == "new"  # persisted to the same store


def test_exchange_failure_surfaces_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error_description": "invalid grant"})

    with pytest.raises(AuthenticationError, match="invalid grant"):
        x_auth.exchange_code("cid", "secret", "bad", "http://cb", "verifier",
                             transport=httpx.MockTransport(handler))


# --- OfficialXClient mapping (MockTransport — no network) ---------------------

def _client(handler) -> OfficialXClient:
    return OfficialXClient(bearer_token="bt", user_access_token="ut",
                           transport=httpx.MockTransport(handler))


def test_search_parses_posts_and_next_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/2/tweets/search/recent"
        return httpx.Response(200, json={"data": [
            {"id": "1", "author_id": "100", "text": "building robots",
             "created_at": "2026-11-13T00:00:00.000Z"}], "meta": {"next_token": "tok"}})

    page = _client(handler).search_recent_posts("robotics", max_results=100)
    assert isinstance(page, Page)
    assert page.data[0].author_id == "100" and page.next_token == "tok"


def test_users_parse_includes_follower_count():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [
            {"id": "100", "username": "robo", "name": "R", "description": "bots",
             "public_metrics": {"followers_count": 42}}]})

    profile = _client(handler).get_users(["100"])[0]
    assert isinstance(profile, Profile) and profile.follower_count == 42


def test_send_dm_returns_ids_and_requires_user_context():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(201, json={"data": {"dm_conversation_id": "c1",
                                                  "dm_event_id": "e1"}})

    result = _client(handler).send_dm("100", "hello")
    assert isinstance(result, SendResult)
    assert result.dm_event_id == "e1"
    assert captured["auth"] == "Bearer ut"  # user context, not the app bearer


def test_dm_send_without_user_token_fails_explicitly():
    client = OfficialXClient(bearer_token="bt", transport=httpx.MockTransport(
        lambda request: httpx.Response(500)))
    with pytest.raises(EndpointUnavailable, match="authorization"):
        client.send_dm("100", "hi")


def test_401_maps_to_authentication_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Unauthorized"})

    with pytest.raises(AuthenticationError, match="401"):
        _client(handler).search_recent_posts("x")


def test_429_maps_to_rate_limit_with_reset():
    import time

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"x-rate-limit-reset": str(int(time.time()) + 900)})

    with pytest.raises(RateLimitError) as err:
        _client(handler).search_recent_posts("x")
    assert 0 < err.value.reset_seconds <= 900


def test_malformed_json_maps_to_malformed_response_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not json</html>")

    with pytest.raises(MalformedResponseError):
        _client(handler).search_recent_posts("x")


def test_timeout_maps_to_request_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow", request=request)

    with pytest.raises(RequestTimeout):
        _client(handler).search_recent_posts("x")


def test_404_maps_to_endpoint_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    with pytest.raises(EndpointUnavailable):
        _client(handler).get_users(["1"])


def test_from_settings_loads_stored_user_token(tmp_path):
    token_path = tmp_path / "tokens.json"
    x_auth.save_tokens({"access_token": "ut", "refresh_token": "rt", "expires_in": 7200}, token_path)
    from unittest.mock import patch
    with patch("src.integrations.x_auth.TOKENS_PATH", token_path):
        client = OfficialXClient.from_settings(Settings(_env_file=None, x_bearer_token="bt"))
    assert client._user_access_token == "ut"
    assert client._bearer == "bt"
