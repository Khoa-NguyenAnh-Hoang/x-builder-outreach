"""UI workflow layer: every operator action goes through these functions.

No business rules live here — they wrap services and shape results into
UI-friendly success/error states so the Streamlit pages stay dumb renderers
(design doc B1) and everything except rendering is unit-testable.
"""

import json
from dataclasses import dataclass

from pydantic import ValidationError

from src.config import Settings
from src.db import store
from src.integrations.x_client import XClient, XClientError
from src.services.consent import (
    EligibilityDecision,
    evaluate_send_eligibility,
    get_consent_state,
)
from src.services.consent import (
    mark_opt_out as _mark_opt_out,
)
from src.services.consent import (
    record_consent as _record_consent,
)
from src.services.dashboard import dashboard_data
from src.services.discovery import DiscoveryQuery
from src.services.drafting import GeneratedDraft, generate_draft
from src.services.pipeline import PipelineResult, discover_and_qualify


@dataclass
class WorkflowError:
    message: str


def run_discovery_workflow(conn, client: XClient, seeds: str, queries: str,
                           max_pages: int = 1) -> PipelineResult | WorkflowError:
    """Validate free-text UI input, run the pipeline, translate hard failures."""
    try:
        query = DiscoveryQuery(
            seeds=[s.strip() for s in seeds.split(",") if s.strip()],
            queries=[t.strip() for t in queries.split(",") if t.strip()],
            max_pages=max_pages,
        )
    except ValidationError as err:
        return WorkflowError(f"invalid discovery input: {err.errors()[0]['msg']}")
    if not query.seeds and not query.queries:
        return WorkflowError("enter at least one seed username or one topic query")
    try:
        return discover_and_qualify(conn, client, query)
    except XClientError as err:
        return WorkflowError(
            f"X API error: {err} — check credentials and entitlements "
            "(docs/x-api-feasibility.md §6)"
        )


def load_candidates(conn) -> list[dict]:
    """All prospects with their qualification, ordered best-first. Empty DB -> []."""
    rows = conn.execute(
        """
        SELECT p.id, p.x_user_id, p.username, p.display_name, p.follower_count,
               p.source, p.source_query, p.bio,
               q.score, q.confidence, q.reasons, q.components
        FROM prospects p
        LEFT JOIN qualification_results q ON q.prospect_id = p.id
        ORDER BY COALESCE(q.score, 0) DESC, p.id ASC
        """
    ).fetchall()
    candidates = []
    for r in rows:
        evidence_count = conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE prospect_id = ?", (r["id"],)
        ).fetchone()[0]
        candidates.append({
            "id": r["id"],
            "x_user_id": r["x_user_id"],
            "username": r["username"],
            "display_name": r["display_name"],
            "follower_count": r["follower_count"],
            "source": r["source"],
            "source_query": r["source_query"],
            "bio": r["bio"],
            "score": r["score"],
            "confidence": r["confidence"],
            "reasons": json.loads(r["reasons"]) if r["reasons"] else [],
            "components": json.loads(r["components"]) if r["components"] else {},
            "evidence_count": evidence_count,
        })
    return candidates


def load_candidate_detail(conn, prospect_id: int) -> dict | WorkflowError:
    prospect = store.get_prospect(conn, prospect_id)
    if prospect is None:
        return WorkflowError(f"unknown candidate {prospect_id}")
    qualification = conn.execute(
        "SELECT * FROM qualification_results WHERE prospect_id = ?", (prospect_id,)
    ).fetchone()
    evidence = conn.execute(
        "SELECT * FROM evidence WHERE prospect_id = ? ORDER BY captured_at DESC, id DESC",
        (prospect_id,),
    ).fetchall()
    drafts = conn.execute(
        "SELECT * FROM drafts WHERE prospect_id = ? ORDER BY id DESC", (prospect_id,)
    ).fetchall()
    return {
        "prospect": dict(prospect),
        "qualification": dict(qualification) if qualification else None,
        "reasons": json.loads(qualification["reasons"]) if qualification else [],
        "components": json.loads(qualification["components"]) if qualification else {},
        "evidence": [dict(e) for e in evidence],
        "drafts": [dict(d) for d in drafts],
        "consent_state": get_consent_state(conn, prospect_id),
    }


def draft_for_candidate(conn, prospect_id: int, llm=None) -> GeneratedDraft | WorkflowError:
    try:
        return generate_draft(conn, prospect_id, llm=llm)
    except Exception as err:  # NoGroundedEvidenceError and any generator failure
        return WorkflowError(f"cannot draft: {err}")


def approve_draft(conn, draft_id: int) -> None:
    store.set_draft_status(conn, draft_id, "approved", approved_at=store.now_iso())


def save_draft_edit(conn, draft_id: int, text: str) -> None:
    store.update_draft_text(conn, draft_id, text)


def check_send_eligibility(conn, prospect_id: int, mode: str, settings: Settings,
                           api_available: bool = True) -> EligibilityDecision:
    return evaluate_send_eligibility(conn, prospect_id, mode, settings,
                                     api_available=api_available)


def mark_opt_out(conn, prospect_id: int, source: str = "operator manual") -> None:
    _mark_opt_out(conn, prospect_id, source)


def record_consent(conn, prospect_id: int, source: str, evidence_url: str | None = None,
                   scope: str = "manual", verified_by: str | None = None) -> None:
    """Raises OptedOutLockedError if the recipient is opted out (I2) — pages show it."""
    _record_consent(conn, prospect_id, source=source, evidence_url=evidence_url,
                    scope=scope, verified_by=verified_by)


def load_dashboard(conn, automated_reply_tracking: bool = False):
    return dashboard_data(conn, automated_reply_tracking=automated_reply_tracking)


def record_manual_reply(conn, prospect_id: int, text: str | None = None):
    from src.services.conversations import record_manual_reply as _record
    try:
        return _record(conn, prospect_id, text)
    except ValueError as err:
        return WorkflowError(str(err))


def ingest_replies(conn, client):
    """Pull DM events via the API; on any client failure the manual path stays active."""
    from src.services.conversations import ingest_reply_events
    try:
        return ingest_reply_events(conn, client)
    except XClientError as err:
        return WorkflowError(
            f"automated reply polling unavailable: {err} — manual tracking stays active"
        )
