import pytest
from pydantic import ValidationError

from src.config import Settings


def test_defaults_match_policy_caps():
    s = Settings(_env_file=None)
    assert s.send_cap_15min == 10
    assert s.send_cap_24h == 40
    assert s.oauth_callback_url == "http://127.0.0.1:8501/callback"


def test_missing_credentials_reported_without_values():
    s = Settings(_env_file=None)
    missing = s.missing_credentials()
    assert sorted(missing) == ["x_bearer_token", "x_client_id", "x_client_secret"]
    # presence-only reporting: status values are bools, never the secret itself
    assert all(isinstance(ok, bool) for ok in s.credentials_status().values())


def test_cap_above_x_limit_rejected_with_actionable_message():
    with pytest.raises(ValidationError) as err:
        Settings(_env_file=None, send_cap_15min=20)
    msg = str(err.value)
    assert "1..15" in msg
    assert "15 DM sends per 15 min" in msg


def test_cap_below_one_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, send_cap_24h=0)
