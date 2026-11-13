"""LIVE X API smoke tests (T07) — opt-in only: `uv run pytest -m live`.

Costs a few cents of credits. Read-only: bearer search + lookup, and (once the
user has run the authorize CLI) the user-context /users/me read. No DM is sent
by these tests — the first controlled send belongs to T13.
"""

import pytest

from src.config import get_settings

pytestmark = pytest.mark.live


def _settings():
    return get_settings()


def test_live_bearer_search_recent():
    from src.integrations.x_client import OfficialXClient

    s = _settings()
    if not s.x_bearer_token:
        pytest.skip("no bearer token in .env")
    page = OfficialXClient(bearer_token=s.x_bearer_token).search_recent_posts(
        "robotics", max_results=10)
    assert all(p.id and p.text for p in page.data)  # well-formed posts came back


def test_live_bearer_user_lookup():
    from src.integrations.x_client import OfficialXClient

    s = _settings()
    if not s.x_bearer_token:
        pytest.skip("no bearer token in .env")
    profiles = OfficialXClient(bearer_token=s.x_bearer_token).get_users_by_usernames(
        ["XDevelopers"])
    assert len(profiles) == 1
    assert profiles[0].username.lower() == "xdevelopers"


def test_live_user_context_me():
    from src.integrations.x_auth import load_tokens
    from src.integrations.x_client import OfficialXClient

    s = _settings()
    tokens = load_tokens()
    if not (s.x_bearer_token and tokens):
        pytest.skip("run `uv run python -m src.integrations.x_auth` once to authorize")
    me = OfficialXClient.from_settings(s).get_me()
    assert me.id and me.username  # the authorized account, read back
    print(f"authorized as @{me.username}")  # handle is not a secret
