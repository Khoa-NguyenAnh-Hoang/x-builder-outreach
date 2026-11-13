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


# --- live implementation (T07) — only the endpoints documented in feasibility §2 ---

import time

import httpx


def _error_detail(resp: "httpx.Response") -> str:
    try:
        body = resp.json()
        detail = body.get("detail") or body.get("error") or body
        return str(detail)[:200]
    except ValueError:
        return resp.text[:200]


def _raise_for_status(resp: "httpx.Response") -> None:
    if resp.status_code < 400:
        return
    if resp.status_code == 429:
        reset = resp.headers.get("x-rate-limit-reset")
        reset_seconds = max(0, int(reset) - int(time.time())) if reset else None
        raise RateLimitError("rate limited by X (429)", reset_seconds=reset_seconds)
    if resp.status_code in (401, 403):
        raise AuthenticationError(f"auth failed ({resp.status_code}): {_error_detail(resp)}")
    if resp.status_code == 404:
        raise EndpointUnavailable("endpoint not found (404) — check entitlements and path")
    raise XClientError(f"X API error {resp.status_code}: {_error_detail(resp)}")


class OfficialXClient:
    """Live XClient. App-only bearer for public reads; user context (OAuth 2.0
    token from x_auth) for DM operations. Missing capabilities fail explicitly."""

    API_BASE = "https://api.x.com"
    TIMEOUT = 15.0
    DM_EVENT_FIELDS = "id,event_type,text,created_at,sender_id,dm_conversation_id"

    def __init__(self, bearer_token: str | None = None,
                 user_access_token: str | None = None,
                 transport: "httpx.BaseTransport | None" = None):
        self._bearer = bearer_token
        self._user_access_token = user_access_token
        self._transport = transport

    @classmethod
    def from_settings(cls, settings, tokens: dict | None = None) -> "OfficialXClient":
        """Bearer from .env; user token from data/tokens.json, refreshed if near expiry."""
        if tokens is None:
            from src.integrations.x_auth import ensure_fresh_tokens, load_tokens
            tokens = ensure_fresh_tokens(settings.x_client_id, settings.x_client_secret,
                                         load_tokens())
        user_token = tokens["access_token"] if tokens else None
        return cls(bearer_token=settings.x_bearer_token, user_access_token=user_token)

    def _headers(self, user_context: bool) -> dict:
        token = self._user_access_token if user_context else self._bearer
        if not token:
            raise EndpointUnavailable(
                "this endpoint needs user authorization — run: "
                "uv run python -m src.integrations.x_auth"
            )
        return {"Authorization": f"Bearer {token}"}

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json_body: dict | None = None, user_context: bool = False) -> dict:
        try:
            # top-level httpx.request can't take a transport — use an explicit Client
            with httpx.Client(timeout=self.TIMEOUT, transport=self._transport) as client:
                resp = client.request(method, self.API_BASE + path, params=params,
                                      json=json_body, headers=self._headers(user_context))
        except httpx.TimeoutException as err:
            raise RequestTimeout(f"X API timeout: {err}") from err
        except httpx.HTTPError as err:
            raise XClientError(f"transport error talking to X: {err}") from err
        _raise_for_status(resp)
        try:
            return resp.json()
        except ValueError as err:
            raise MalformedResponseError(f"non-JSON response from {path}") from err

    def search_recent_posts(self, query: str, *, max_results: int = 100,
                            next_token: str | None = None) -> Page:
        params = {"query": query, "max_results": max(10, min(100, max_results)),
                  "tweet.fields": "created_at,author_id"}
        if next_token:
            params["next_token"] = next_token
        payload = self._request("GET", "/2/tweets/search/recent", params=params)
        try:
            posts = [Post.model_validate(p) for p in payload.get("data") or []]
        except Exception as err:
            raise MalformedResponseError(f"unexpected search response shape: {err}") from err
        return Page(data=posts, next_token=(payload.get("meta") or {}).get("next_token"))

    @staticmethod
    def _profile(p: dict) -> Profile:
        try:
            return Profile(
                id=str(p["id"]), username=p["username"], name=p.get("name"),
                description=p.get("description"),
                follower_count=(p.get("public_metrics") or {}).get("followers_count"),
            )
        except KeyError as err:
            raise MalformedResponseError(f"profile response missing {err}") from err

    def get_users(self, user_ids: list[str]) -> list[Profile]:
        payload = self._request("GET", "/2/users", params={
            "ids": ",".join(user_ids), "user.fields": "name,description,public_metrics"})
        return [self._profile(p) for p in payload.get("data") or []]

    def get_users_by_usernames(self, usernames: list[str]) -> list[Profile]:
        payload = self._request("GET", "/2/users/by", params={
            "usernames": ",".join(usernames), "user.fields": "name,description,public_metrics"})
        return [self._profile(p) for p in payload.get("data") or []]

    def get_me(self) -> Profile:
        """The authorized account itself (read smoke + 'connected as' display)."""
        payload = self._request("GET", "/2/users/me",
                                params={"user.fields": "name,description,public_metrics"},
                                user_context=True)
        return self._profile(payload["data"])

    def send_dm(self, participant_id: str, text: str) -> SendResult:
        payload = self._request(
            "POST", f"/2/dm_conversations/with/{participant_id}/messages",
            json_body={"text": text}, user_context=True)
        data = payload.get("data", payload)
        try:
            return SendResult(dm_conversation_id=data["dm_conversation_id"],
                              dm_event_id=data["dm_event_id"])
        except KeyError as err:
            raise MalformedResponseError(f"send-DM response missing {err}") from err

    def get_dm_events(self, *, participant_id: str | None = None,
                      conversation_id: str | None = None) -> list[DMEventPayload]:
        if conversation_id:
            path, params = f"/2/dm_conversations/{conversation_id}/dm_events", {}
        elif participant_id:
            path = f"/2/dm_conversations/with/{participant_id}/dm_events"
            params = {"dm_event.fields": self.DM_EVENT_FIELDS}
        else:
            path = "/2/dm_events"
            params = {"max_results": 100, "event_types": "MessageCreate",
                      "dm_event.fields": self.DM_EVENT_FIELDS}
        payload = self._request("GET", path, params=params, user_context=True)
        try:
            return [DMEventPayload(
                id=str(e["id"]), event_type=e["event_type"],
                conversation_id=e.get("dm_conversation_id"), sender_id=e.get("sender_id"),
                text=e.get("text"), created_at=e.get("created_at"),
            ) for e in payload.get("data") or []]
        except KeyError as err:
            raise MalformedResponseError(f"dm_events response missing {err}") from err
