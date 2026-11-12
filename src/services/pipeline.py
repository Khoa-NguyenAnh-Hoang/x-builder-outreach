"""T08+T09 pipeline glue: discover -> ingest evidence -> qualify -> persist.

This is the single entry point the UI (T11) will call. Every qualified candidate
ends up with at least one inspectable evidence item whenever profile data exists.
"""

import sqlite3
from dataclasses import dataclass, field

from src.db import store
from src.integrations.x_client import XClient
from src.models import Qualification
from src.services.discovery import DiscoveryQuery, DiscoveryRunResult, run_discovery
from src.services.evidence import ingest_post, ingest_profile
from src.services.qualification import qualify_and_persist


@dataclass
class PipelineResult:
    run: DiscoveryRunResult
    qualifications: dict[str, Qualification] = field(default_factory=dict)  # x_user_id -> result
    evidence_skipped: list[str] = field(default_factory=list)  # warnings for skipped post evidence


def discover_and_qualify(conn: sqlite3.Connection, client: XClient,
                         query: DiscoveryQuery) -> PipelineResult:
    run = run_discovery(conn, client, query)
    result = PipelineResult(run=run)

    for x_user_id, profile in run.profiles.items():
        row = store.get_prospect_by_x_user_id(conn, x_user_id)
        if row is None:  # defensive: discovery just upserted this candidate
            continue
        prospect_id = row["id"]
        ingest_profile(conn, prospect_id, profile)
        posts = run.posts_by_author.get(x_user_id, [])
        for post in posts:
            ingest_post(conn, prospect_id, post, profile)
        result.qualifications[x_user_id] = qualify_and_persist(
            conn, prospect_id, profile, posts
        )

    return result
