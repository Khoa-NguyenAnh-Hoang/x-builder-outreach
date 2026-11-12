"""T15 — outreach history and attention-needed dashboard.

Read-only reporting over the DB: every number here is derived from real rows,
never placeholders. Ambiguous (`unknown`) sends are the top attention item —
they must be reconciled before any retry (invariant I7).
"""

import sqlite3

from pydantic import BaseModel


class AttemptView(BaseModel):
    attempt_id: int
    prospect_id: int
    x_user_id: str
    username: str | None
    mode: str
    status: str
    deny_reason: str | None
    x_conversation_id: str | None
    x_event_id: str | None
    requested_at: str
    resolved_at: str | None


class ReplyView(BaseModel):
    event_id: int
    prospect_id: int | None
    username: str | None
    attempt_id: int | None
    source: str  # api | manual (derived from the event id prefix)
    text: str | None
    occurred_at: str | None


class DashboardData(BaseModel):
    status_counts: dict[str, int] = {}
    total_attempts: int = 0
    replied_count: int = 0
    opted_out_count: int = 0
    attention: list[AttemptView] = []
    recent_attempts: list[AttemptView] = []
    replies: list[ReplyView] = []
    tracking_mode: str = "manual"  # manual | api


def _attempt_view(row: sqlite3.Row) -> AttemptView:
    return AttemptView(
        attempt_id=row["id"],
        prospect_id=row["prospect_id"],
        x_user_id=row["x_user_id"],
        username=row["username"],
        mode=row["mode"],
        status=row["status"],
        deny_reason=row["deny_reason"],
        x_conversation_id=row["x_conversation_id"],
        x_event_id=row["x_event_id"],
        requested_at=row["requested_at"],
        resolved_at=row["resolved_at"],
    )


def _attempts(conn: sqlite3.Connection, where: str = "", params=()) -> list[AttemptView]:
    rows = conn.execute(
        f"""
        SELECT a.*, p.x_user_id, p.username
        FROM outreach_attempts a
        JOIN prospects p ON p.id = a.prospect_id
        {where}
        ORDER BY a.requested_at DESC, a.id DESC
        """,
        params,
    ).fetchall()
    return [_attempt_view(r) for r in rows]


def dashboard_data(conn: sqlite3.Connection, automated_reply_tracking: bool = False) -> DashboardData:
    counts = {
        row["status"]: row["n"]
        for row in conn.execute(
            "SELECT status, COUNT(*) AS n FROM outreach_attempts GROUP BY status"
        ).fetchall()
    }
    replied = conn.execute(
        "SELECT COUNT(*) FROM dm_events WHERE event_type = 'MessageCreate' "
        "AND prospect_id IS NOT NULL"
    ).fetchone()[0]
    opted_out = conn.execute(
        "SELECT COUNT(*) FROM consent_records WHERE opted_out_at IS NOT NULL"
    ).fetchone()[0]

    # attention: ambiguous unknowns first, then real send failures (not policy denials)
    attention = _attempts(
        conn,
        "WHERE a.status = 'unknown' OR (a.status = 'failed' AND a.deny_reason IS NULL)",
    )
    attention.sort(key=lambda a: 0 if a.status == "unknown" else 1)

    replies = [
        ReplyView(
            event_id=r["id"],
            prospect_id=r["prospect_id"],
            username=r["username"],
            attempt_id=r["outreach_attempt_id"],
            source="manual" if r["x_dm_event_id"].startswith("manual-") else "api",
            text=r["text"],
            occurred_at=r["occurred_at"],
        )
        for r in conn.execute(
            """
            SELECT d.*, p.username
            FROM dm_events d
            LEFT JOIN prospects p ON p.id = d.prospect_id
            WHERE d.event_type = 'MessageCreate' AND d.prospect_id IS NOT NULL
            ORDER BY d.ingested_at DESC, d.id DESC
            """
        ).fetchall()
    ]

    return DashboardData(
        status_counts=counts,
        total_attempts=sum(counts.values()),
        replied_count=replied,
        opted_out_count=opted_out,
        attention=attention,
        recent_attempts=_attempts(conn)[:50],
        replies=replies,
        tracking_mode="api" if automated_reply_tracking else "manual",
    )
