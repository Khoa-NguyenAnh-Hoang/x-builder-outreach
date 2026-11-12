"""X client boundary (T06).

Services depend on the XClient protocol and these exception types — never on
httpx or raw HTTP. The real HTTP implementation arrives in T07 against only the
endpoints documented in docs/x-api-feasibility.md; every error type here maps to
one documented failure mode so services can handle them explicitly.
"""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

# --- exception hierarchy: one type per documented failure mode ---

class XClientError(Exception):
    """Base for every error the X client boundary can raise."""


class AuthenticationError(XClientError):
    """Credentials missing, invalid, or rejected (HTTP 401/403)."""


class RateLimitError(XClientError):
    """HTTP 429 — includes the reset window when X provides it."""

    def __init__(self, message: str, *, reset_seconds: int | None = None):
        super().__init__(message)
        self.reset_seconds = reset_seconds


class MalformedResponseError(XClientError):
    """Response did not match the documented schema (T01 evidence)."""


class RequestTimeout(XClientError):
    """Network timeout talking to the API."""


class EndpointUnavailable(XClientError):
    """The account is not entitled to this endpoint (docs §6 console check).

    Clients must raise this instead of silently simulating success — a missing
    capability must never look like an empty-but-valid result.
    """


# --- API-shaped result models (transport payloads, not DB rows) ---

class Post(BaseModel):
    id: str
    author_id: str
    text: str
    created_at: str | None = None


class Profile(BaseModel):
    id: str
    username: str
    name: str | None = None
    description: str | None = None
    follower_count: int | None = None


class SendResult(BaseModel):
    dm_conversation_id: str
    dm_event_id: str


class DMEventPayload(BaseModel):
    id: str
    event_type: str  # MessageCreate | ParticipantsJoin | ParticipantsLeave
    conversation_id: str | None = None
    sender_id: str | None = None
    text: str | None = None
    created_at: str | None = None


class Page(BaseModel):
    data: list[Post]
    next_token: str | None = None


# --- the boundary ---

@runtime_checkable
class XClient(Protocol):
    """Only the four capabilities documented in docs/x-api-feasibility.md §2."""

    def search_recent_posts(
        self, query: str, *, max_results: int = 100, next_token: str | None = None
    ) -> Page: ...

    def get_users(self, user_ids: list[str]) -> list[Profile]: ...

    def get_users_by_usernames(self, usernames: list[str]) -> list[Profile]:
        """GET /2/users/by — documented in docs/x-api-feasibility.md §2 row (b);
        added in T08 for seed-username discovery."""
        ...

    def send_dm(self, participant_id: str, text: str) -> SendResult: ...

    def get_dm_events(
        self,
        *,
        participant_id: str | None = None,
        conversation_id: str | None = None,
    ) -> list[DMEventPayload]: ...
