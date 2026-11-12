"""T09 (part 1) — evidence ingestion: persist profile/post evidence with URL, source type,
capture time, and text. Dedup-by-URL is the T05 store's guarantee; repeated runs refresh
capture time instead of duplicating rows."""

import sqlite3

from src.db import store
from src.integrations.x_client import Post, Profile
from src.models import Evidence


def profile_url(profile: Profile) -> str:
    return f"https://x.com/{profile.username}"


def post_url(profile: Profile, post: Post) -> str:
    return f"https://x.com/{profile.username}/status/{post.id}"


def ingest_profile(conn: sqlite3.Connection, prospect_id: int, profile: Profile) -> int:
    text = " ".join(v for v in (profile.name, profile.description) if v) or None
    return store.upsert_evidence(conn, Evidence(
        prospect_id=prospect_id,
        url=profile_url(profile),
        source_type="profile",
        text=text,
    ))


def ingest_post(conn: sqlite3.Connection, prospect_id: int, post: Post, profile: Profile) -> int:
    return store.upsert_evidence(conn, Evidence(
        prospect_id=prospect_id,
        url=post_url(profile, post),
        source_type="post",
        text=post.text,
        # captured_at is set by the store; the post's own created_at drives freshness scoring
    ))
