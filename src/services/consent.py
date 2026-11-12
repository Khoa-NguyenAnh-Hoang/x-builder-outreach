"""T12 — consent capture and the send-eligibility gate (design doc A3).

This module IS the compliance gate: every send decision goes through
evaluate_send_eligibility. The UI renders its output; it never overrides it.
"""

import sqlite3
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from src.config import Settings
from src.db import store
from src.models import ConsentRecord


class OptedOutLockedError(Exception):
    """Raised when an operation would weaken an existing opt-out (invariant I2)."""


class ConsentState(BaseModel):
    opted_out: bool
    consent: str  # none | pending | verified
    consent_source: str | None = None
    approved_draft_id: int | None = None


class EligibilityCheck(BaseModel):
    name: str
    invariant: str  # I1..I7 / T01
    passed: bool
    detail: str


class EligibilityDecision(BaseModel):
    allowed: bool
    reason: str
    checks: list[EligibilityCheck] = []


MODES = ("operator_approved", "dev_test", "automated_batch")


def _existing(conn: sqlite3.Connection, prospect_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM consent_records WHERE prospect_id = ?", (prospect_id,)
    ).fetchone()


def get_consent_state(conn: sqlite3.Connection, prospect_id: int) -> ConsentState:
    row = _existing(conn, prospect_id)
    opted_out = bool(row and row["opted_out_at"])
    consent = "none"
    if row:
        consent = "verified" if row["verified_at"] else "pending"
    approved = conn.execute(
        "SELECT id FROM drafts WHERE prospect_id = ? AND status = 'approved' "
        "ORDER BY id DESC LIMIT 1",
        (prospect_id,),
    ).fetchone()
    return ConsentState(
        opted_out=opted_out,
        consent=consent,
        consent_source=row["source"] if row else None,
        approved_draft_id=approved["id"] if approved else None,
    )


def record_consent(conn: sqlite3.Connection, prospect_id: int, source: str,
                   evidence_url: str | None = None, scope: str = "manual",
                   verified_by: str | None = None) -> int:
    """Capture recipient consent for automated/batch or test sends.

    Never weakens an existing opt-out: recording consent for an opted-out
    recipient raises instead of silently clearing suppression (I2).
    """
    existing = _existing(conn, prospect_id)
    if existing and existing["opted_out_at"]:
        raise OptedOutLockedError(
            "recipient is opted out — consent records cannot override suppression (I2)"
        )
    return store.upsert_consent(conn, ConsentRecord(
        prospect_id=prospect_id,
        source=source,
        evidence_url=evidence_url,
        scope=scope,
        verified_by=verified_by,
        verified_at=store.now_iso() if verified_by else None,
        opted_out_at=existing["opted_out_at"] if existing else None,
    ))


def verify_consent(conn: sqlite3.Connection, prospect_id: int, verified_by: str) -> int:
    existing = _existing(conn, prospect_id)
    if existing and existing["opted_out_at"]:
        raise OptedOutLockedError("recipient is opted out (I2)")
    if existing is None:
        raise ValueError("no consent record to verify — record consent first")
    return store.upsert_consent(conn, ConsentRecord(
        prospect_id=prospect_id,
        source=existing["source"],
        evidence_url=existing["evidence_url"],
        scope=existing["scope"],
        verified_by=verified_by,
        verified_at=store.now_iso(),
        opted_out_at=existing["opted_out_at"],
    ))


def mark_opt_out(conn: sqlite3.Connection, prospect_id: int, source: str = "operator manual") -> int:
    """Suppression is immediate and permanent; it keeps any consent record fields (I2)."""
    existing = _existing(conn, prospect_id)
    return store.upsert_consent(conn, ConsentRecord(
        prospect_id=prospect_id,
        source=existing["source"] if existing else source,
        evidence_url=existing["evidence_url"] if existing else None,
        scope=existing["scope"] if existing else "suppression",
        verified_by=existing["verified_by"] if existing else None,
        verified_at=existing["verified_at"] if existing else None,
        opted_out_at=store.now_iso(),
    ))


def consume_approval(conn: sqlite3.Connection, prospect_id: int) -> int:
    """I1: approval binds to one send. Called by T13 after a send reaches a
    terminal state; approved drafts return to 'superseded' and must be re-approved."""
    cur = conn.execute(
        "UPDATE drafts SET status = 'superseded' WHERE prospect_id = ? AND status = 'approved'",
        (prospect_id,),
    )
    conn.commit()
    return cur.rowcount


def _window_counts(conn: sqlite3.Connection, now: datetime) -> tuple[int, int]:
    since_15 = (now - timedelta(minutes=15)).isoformat(timespec="seconds")
    since_24 = (now - timedelta(hours=24)).isoformat(timespec="seconds")
    c15 = conn.execute(
        "SELECT COUNT(*) FROM outreach_attempts "
        "WHERE status IN ('intent', 'sent', 'unknown') AND requested_at >= ?",
        (since_15,),
    ).fetchone()[0]
    c24 = conn.execute(
        "SELECT COUNT(*) FROM outreach_attempts "
        "WHERE status IN ('intent', 'sent', 'unknown') AND requested_at >= ?",
        (since_24,),
    ).fetchone()[0]
    return c15, c24


def evaluate_send_eligibility(
    conn: sqlite3.Connection,
    prospect_id: int,
    mode: str,
    settings: Settings,
    *,
    now: datetime | None = None,
    api_available: bool = True,
) -> EligibilityDecision:
    """The single send gate (design doc A3). Order matters: opt-out first, always."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    now = now or datetime.now(UTC)
    state = get_consent_state(conn, prospect_id)
    checks: list[EligibilityCheck] = []

    def check(name: str, invariant: str, passed: bool, fail_detail: str) -> None:
        checks.append(EligibilityCheck(
            name=name, invariant=invariant, passed=passed,
            detail="ok" if passed else fail_detail,
        ))

    check("opt-out suppression", "I2", not state.opted_out,
          "recipient is opted out — sending permanently suppressed")
    check("per-message operator approval", "I1", state.approved_draft_id is not None,
          "no approved draft for this recipient — review and approve the current text first")
    # mode rules
    if mode == "dev_test":
        allowlist = settings.test_allowlist_ids()
        row = conn.execute(
            "SELECT x_user_id FROM prospects WHERE id = ?", (prospect_id,)
        ).fetchone()
        in_list = bool(row and row["x_user_id"] in allowlist)
        check("test-recipient allowlist", "I4", in_list,
              "dev/test sends target only the operator's own or consenting accounts "
              f"(allowlist: {sorted(allowlist) or 'empty'})")
    elif mode == "automated_batch":
        check("verified recipient opt-in", "I3", state.consent == "verified",
              f"automated/batch sending requires verified opt-in (current state: {state.consent})")
    else:  # operator_approved
        check("one-to-one operator-approved send", "I1", True,
              "per-message review done; still subject to caps, dedup and opt-out")

    c15, c24 = _window_counts(conn, now)
    check("volume caps", "I5",
          c15 < settings.send_cap_15min and c24 < settings.send_cap_24h,
          f"{c15}/{settings.send_cap_15min} sends in the last 15 min, "
          f"{c24}/{settings.send_cap_24h} in the last 24 h")
    check("no active outreach attempt", "I7",
          not store.has_active_attempt(conn, prospect_id),
          "an intent/sent/unknown attempt already exists for this recipient — "
          "duplicate sends are blocked")
    check("X API available", "T01", api_available,
          "X API is marked unavailable — sending is blocked, not simulated")

    first_fail = next((c for c in checks if not c.passed), None)
    return EligibilityDecision(
        allowed=first_fail is None,
        reason=first_fail.name if first_fail else "all checks passed",
        checks=checks,
    )
