"""T08 — narrow prospect discovery from seed usernames and/or focused topic queries.

Bounded by design: page count is capped, rate-limit hits stop paging gracefully
(partial results kept, warning recorded), and only the two documented read
endpoints are used (recent search + user lookup). Repeated runs upsert the same
X user IDs instead of creating duplicates (T05 store guarantee).
"""

import sqlite3

from pydantic import BaseModel, Field, field_validator

from src.db import store
from src.integrations.x_client import (
    AuthenticationError,
    EndpointUnavailable,
    Page,
    Post,
    Profile,
    RateLimitError,
    XClient,
)
from src.models import Prospect

MAX_PAGES = 3  # hard bound; DiscoveryQuery.max_pages cannot exceed this
LOOKUP_CHUNK = 100  # documented per-request cap for user lookup


class DiscoveryQuery(BaseModel):
    seeds: list[str] = Field(default_factory=list)   # usernames, e.g. ["robo_builder"]
    queries: list[str] = Field(default_factory=list)  # focused topics, e.g. ["humanoid robots founders"]
    max_pages: int = 1                                # per query, bounded by MAX_PAGES

    @field_validator("max_pages")
    @classmethod
    def _bounded(cls, v: int) -> int:
        if not 1 <= v <= MAX_PAGES:
            raise ValueError(f"max_pages must be 1..{MAX_PAGES} — discovery is deliberately narrow")
        return v


class DiscoveryRunResult(BaseModel):
    candidates_upserted: int = 0
    new_candidates: int = 0
    profiles: dict[str, Profile] = {}            # x_user_id -> profile (evidence/username source)
    posts_by_author: dict[str, list[Post]] = {}  # x_user_id -> recent posts (evidence source)
    warnings: list[str] = []


def _upsert_candidate(conn: sqlite3.Connection, profile: Profile, source: str,
                      source_query: str | None, result: DiscoveryRunResult) -> None:
    existing = store.get_prospect_by_x_user_id(conn, profile.id)
    store.upsert_prospect(conn, Prospect(
        x_user_id=profile.id,
        username=profile.username,
        display_name=profile.name,
        bio=profile.description,
        follower_count=profile.follower_count,
        source=source,
        source_query=source_query,
    ))
    result.candidates_upserted += 1
    if existing is None:
        result.new_candidates += 1
    result.profiles[profile.id] = profile


def _paged_search(client: XClient, query: str, q: DiscoveryQuery,
                  result: DiscoveryRunResult) -> list[Post]:
    """Search one topic with bounded pagination; a rate-limit hit keeps partial results."""
    posts: list[Post] = []
    next_token: str | None = None
    for page_no in range(1, q.max_pages + 1):
        try:
            page: Page = client.search_recent_posts(query, max_results=100, next_token=next_token)
        except RateLimitError as err:
            result.warnings.append(
                f"rate limited during '{query}' at page {page_no}"
                + (f" (reset in {err.reset_seconds}s)" if err.reset_seconds else "")
                + " — kept partial results"
            )
            break
        posts.extend(page.data)
        if not page.next_token:
            break
        next_token = page.next_token
    return posts


def run_discovery(conn: sqlite3.Connection, client: XClient, q: DiscoveryQuery) -> DiscoveryRunResult:
    result = DiscoveryRunResult()

    # 1. Seeds: username lookup -> candidates (source="seed")
    if q.seeds:
        try:
            profiles = client.get_users_by_usernames(q.seeds)
        except (AuthenticationError, EndpointUnavailable):
            raise  # actionable at the UI layer
        found = {p.username.lower(): p for p in profiles if p.username}
        for seed in q.seeds:
            profile = found.get(seed.lower())
            if profile is None:
                result.warnings.append(f"seed '{seed}' not found — skipped")
                continue
            _upsert_candidate(conn, profile, source="seed", source_query=None, result=result)

    # 2. Topic queries: recent search -> author lookup -> candidates (source="search")
    for topic in q.queries:
        posts = _paged_search(client, topic, q, result)
        author_ids: list[str] = []
        for post in posts:
            if post.author_id not in author_ids:
                author_ids.append(post.author_id)
        for chunk_start in range(0, len(author_ids), LOOKUP_CHUNK):
            chunk = author_ids[chunk_start:chunk_start + LOOKUP_CHUNK]
            try:
                profiles = client.get_users(chunk)
            except (AuthenticationError, EndpointUnavailable):
                raise
            by_id = {p.id: p for p in profiles}
            for author_id in author_ids:
                profile = by_id.get(author_id)
                if profile is None:
                    continue  # suspended/deleted author — no candidate
                _upsert_candidate(conn, profile, source="search", source_query=topic, result=result)
                result.posts_by_author.setdefault(author_id, []).extend(
                    p for p in posts if p.author_id == author_id
                )
    return result
