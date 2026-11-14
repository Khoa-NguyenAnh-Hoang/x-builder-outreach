"""Typed application settings loaded from environment / .env (policy I9: secrets never logged or committed)."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # X API credentials — optional at startup so the app can show a
    # disconnected state with setup guidance instead of crashing.
    x_bearer_token: str | None = None
    x_client_id: str | None = None
    x_client_secret: str | None = None
    oauth_callback_url: str = "http://127.0.0.1:8501/callback"

    # Volume caps (policy I5) — must stay inside X's documented per-user DM limits.
    send_cap_15min: int = 10
    send_cap_24h: int = 40

    # Comma-separated X user IDs allowed as dev/test recipients (policy I4).
    test_recipient_allowlist: str = ""

    # Optional AI drafting provider (D3=B: Groq free tier, user-approved 13 Nov 2026;
    # Mistral preset removed 14 Nov — key access lost).
    groq_api_key: str | None = None

    @model_validator(mode="after")
    def _caps_within_x_limits(self) -> "Settings":
        if not (0 < self.send_cap_15min <= 15):
            raise ValueError(
                "SEND_CAP_15MIN must be 1..15 (X allows 15 DM sends per 15 min per user); "
                "fix the value in .env"
            )
        if not (0 < self.send_cap_24h <= 1440):
            raise ValueError(
                "SEND_CAP_24H must be 1..1440 (X allows 1,440 DM sends per 24 h per user); "
                "fix the value in .env"
            )
        return self

    def credentials_status(self) -> dict[str, bool]:
        """Which credentials are present. Report presence only — never values (I9)."""
        return {
            "x_bearer_token": bool(self.x_bearer_token),
            "x_client_id": bool(self.x_client_id),
            "x_client_secret": bool(self.x_client_secret),
        }

    def missing_credentials(self) -> list[str]:
        return [name for name, ok in self.credentials_status().items() if not ok]

    def test_allowlist_ids(self) -> set[str]:
        return {v.strip() for v in self.test_recipient_allowlist.split(",") if v.strip()}

    def secret_values(self) -> tuple[str, ...]:
        """Values the logging redaction filter must scrub from any output (I9)."""
        vals = (self.x_bearer_token, self.x_client_secret, self.groq_api_key)
        return tuple(v for v in vals if v)


@lru_cache
def get_settings() -> Settings:
    return Settings()
