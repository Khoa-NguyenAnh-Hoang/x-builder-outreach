"""Deterministic in-memory X client for tests and offline demos.

Always labelled fake: generated ids carry a `fake-` prefix so a test can never
mistake fake output for live API data. Two failure controls:
- `fail_next(method, error)` — one-shot scripted error (auth, rate limit, timeout, ...)
- `unavailable={...}` — endpoints the account is not entitled to; every call
  raises EndpointUnavailable permanently (never simulates success).
"""

from src.integrations.x_client import (
    DMEventPayload,
    EndpointUnavailable,
    Page,
    Post,
    Profile,
    SendResult,
)


class FakeXClient:
    def __init__(
        self,
        *,
        posts: list[Post] | None = None,
        profiles: list[Profile] | None = None,
        send_results: list[SendResult] | None = None,
        dm_events: list[DMEventPayload] | None = None,
        unavailable: set[str] | None = None,
    ):
        self._posts = list(posts or [])
        self._profiles = list(profiles or [])
        self._send_results = list(send_results or [])
        self._dm_events = list(dm_events or [])
        self._unavailable = set(unavailable or ())
        self._errors: dict[str, list[Exception]] = {}
        # call recording: later tests assert services call the boundary correctly
        self.search_calls: list[dict] = []
        self.get_users_calls: list[list[str]] = []
        self.send_calls: list[tuple[str, str]] = []
        self.dm_events_calls: list[dict] = []

    def fail_next(self, method: str, error: Exception) -> None:
        """Queue a one-shot error for the named method's next call."""
        self._errors.setdefault(method, []).append(error)

    def _pop_error(self, method: str) -> Exception | None:
        errors = self._errors.get(method)
        return errors.pop(0) if errors else None

    def _check_unavailable(self, method: str) -> None:
        if method in self._unavailable:
            raise EndpointUnavailable(f"{method} is not entitled for this account")

    def search_recent_posts(
        self, query: str, *, max_results: int = 100, next_token: str | None = None
    ) -> Page:
        self.search_calls.append(
            {"query": query, "max_results": max_results, "next_token": next_token}
        )
        self._check_unavailable("search_recent_posts")
        error = self._pop_error("search_recent_posts")
        if error:
            raise error
        taken, self._posts = self._posts[:max_results], self._posts[max_results:]
        return Page(data=taken, next_token=None)

    def get_users(self, user_ids: list[str]) -> list[Profile]:
        self.get_users_calls.append(list(user_ids))
        self._check_unavailable("get_users")
        error = self._pop_error("get_users")
        if error:
            raise error
        wanted = set(user_ids)
        return [p for p in self._profiles if p.id in wanted]

    def send_dm(self, participant_id: str, text: str) -> SendResult:
        self.send_calls.append((participant_id, text))
        self._check_unavailable("send_dm")
        error = self._pop_error("send_dm")
        if error:
            raise error
        if self._send_results:
            return self._send_results.pop(0)
        n = len(self.send_calls)
        return SendResult(dm_conversation_id=f"fake-conv-{n}", dm_event_id=f"fake-evt-{n}")

    def get_dm_events(
        self,
        *,
        participant_id: str | None = None,
        conversation_id: str | None = None,
    ) -> list[DMEventPayload]:
        self.dm_events_calls.append(
            {"participant_id": participant_id, "conversation_id": conversation_id}
        )
        self._check_unavailable("get_dm_events")
        error = self._pop_error("get_dm_events")
        if error:
            raise error
        if participant_id is None and conversation_id is None:
            return list(self._dm_events)
        return [
            e
            for e in self._dm_events
            if (participant_id is not None and e.sender_id == participant_id)
            or (conversation_id is not None and e.conversation_id == conversation_id)
        ]
