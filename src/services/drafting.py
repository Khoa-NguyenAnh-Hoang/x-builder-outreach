"""T10 — evidence-grounded message drafting.

Rules enforced here for EVERY generator (template or approved LLM):
- each personalized claim references a stored evidence item (evidence_id)
- the claim text is a verbatim snippet of that evidence AND appears in the draft
- fabricated familiarity (claimed shared history) is rejected outright
- unsupported claims -> the whole proposal is rejected and the deterministic
  template path takes over (recorded as used_fallback)
"""

import re
import sqlite3

from pydantic import BaseModel

from src.db import store
from src.integrations.llm_client import (
    CandidateContext,
    ClaimRef,
    DraftProposal,
    EvidenceBundle,
    LLMClient,
)
from src.models import Draft
from src.services.qualification import AI_TERMS, ROBOTICS_TERMS, match_terms

SNIPPET_LIMIT = 120

FABRICATION_PATTERNS = [
    r"\bwe\s+met\b",
    r"\bas\s+we\s+discussed\b",
    r"\bgreat\s+meeting\b",
    r"\bwhen\s+we\s+spoke\b",
    r"\bi\s+know\s+you\b",
    r"\bour\s+conversation\b",
    r"\bthanks\s+for\s+coming\b",
]


class NoGroundedEvidenceError(Exception):
    """No text evidence is stored for this prospect — nothing honest to personalize."""


class GeneratedDraft(BaseModel):
    draft_id: int
    prospect_id: int
    text: str
    claims: list[ClaimRef] = []
    generator: str
    used_fallback: bool = False
    rejected_reasons: list[str] = []


def _snippet(text: str, limit: int = SNIPPET_LIMIT) -> str:
    """First sentence (or word-bounded truncation) kept verbatim so the
    claim-substring checks hold against the stored evidence text."""
    stripped = text.strip()
    first = re.split(r"(?<=[.!?])\s+", stripped, maxsplit=1)[0]
    if len(first) <= limit:
        return first
    cut = stripped[:limit]
    return cut[: cut.rfind(" ")] if " " in cut else cut


def _domain(evidence_rows) -> str:
    joined = " ".join(r["text"] for r in evidence_rows)
    if match_terms(joined, ROBOTICS_TERMS):
        return "robotics and embodied AI"
    if match_terms(joined, AI_TERMS):
        return "AI and machine learning"
    return "AI and robotics"


def _purpose_sentence(context: CandidateContext, evidence_rows) -> str:
    domain = _domain(evidence_rows)
    who = context.display_name or (
        f"@{context.username}" if context.username else "there"
    )
    return (
        f"Hi {who},\n\nWe're building an AI ecosystem across Southeast Asia and are "
        f"speaking with {domain} builders and researchers. "
        "Would you be open to a short conversation?"
    )


def _template_proposal(context: CandidateContext, evidence_rows) -> DraftProposal:
    """Deterministic draft: every observation is a verbatim quoted snippet from stored
    evidence, so the claim contract holds by construction."""
    claims: list[ClaimRef] = []
    sentences: list[str] = []
    profile_row = next((r for r in evidence_rows if r["source_type"] == "profile"), None)
    post_row = next((r for r in evidence_rows if r["source_type"] == "post"), None)

    if profile_row:
        snippet = _snippet(profile_row["text"])
        claims.append(ClaimRef(evidence_id=profile_row["id"], claim_text=snippet))
        sentences.append(f'I came across your profile — "{snippet}".')
    if post_row:
        snippet = _snippet(post_row["text"])
        claims.append(ClaimRef(evidence_id=post_row["id"], claim_text=snippet))
        sentences.append(f'Your recent post — "{snippet}" — stood out.')

    who = context.display_name or (f"@{context.username}" if context.username else "there")
    text = (
        f"Hi {who},\n\n"
        + (" ".join(sentences) + "\n\n" if sentences else "")
        + (
            "We're building an AI ecosystem across Southeast Asia and are speaking "
            f"with {_domain(evidence_rows)} builders and researchers. "
            "Would you be open to a short conversation?"
        )
    )
    return DraftProposal(text=text, claims=claims, generator="template")


def validate_proposal(proposal: DraftProposal, evidence_rows) -> list[str]:
    """Every problem that disqualifies a proposal. Empty list = acceptable."""
    problems: list[str] = []
    evidence_map = {r["id"]: r for r in evidence_rows}
    has_text_evidence = any(r["text"] for r in evidence_rows)

    if has_text_evidence and not proposal.claims:
        problems.append("no evidence-grounded claims — personalisation is required")
    for claim in proposal.claims:
        row = evidence_map.get(claim.evidence_id)
        if row is None:
            problems.append(f"claim references unknown evidence id {claim.evidence_id}")
        elif claim.claim_text.lower() not in (row["text"] or "").lower():
            problems.append(
                f"claim '{claim.claim_text[:40]}…' not grounded in evidence {claim.evidence_id}"
            )
        if claim.claim_text.lower() not in proposal.text.lower():
            problems.append(f"claim '{claim.claim_text[:40]}…' does not appear in the draft text")
    for pattern in FABRICATION_PATTERNS:
        if re.search(pattern, proposal.text, re.IGNORECASE):
            problems.append(f"fabricated-familiarity pattern detected: /{pattern}/")
    if not proposal.text.strip():
        problems.append("empty draft text")
    return problems


def generate_draft(
    conn: sqlite3.Connection, prospect_id: int, llm: LLMClient | None = None
) -> GeneratedDraft:
    prospect = store.get_prospect(conn, prospect_id)
    if prospect is None:
        raise ValueError(f"unknown prospect {prospect_id}")
    evidence_rows = store.get_evidence_for_prospect(conn, prospect_id)
    if not evidence_rows:
        raise NoGroundedEvidenceError(
            "no stored text evidence for this prospect — run discovery/qualification first; "
            "drafting without evidence would fabricate"
        )

    context = CandidateContext(
        x_user_id=prospect["x_user_id"],
        username=prospect["username"],
        display_name=prospect["display_name"],
    )
    bundles = [
        EvidenceBundle(evidence_id=r["id"], url=r["url"], source_type=r["source_type"], text=r["text"])
        for r in evidence_rows
    ]

    used_fallback = False
    rejected_reasons: list[str] = []
    proposal: DraftProposal | None = None
    if llm is not None:
        try:
            candidate_proposal = llm.propose(context, bundles)
        except Exception as err:  # an LLM failure must never block the deterministic path
            used_fallback = True
            rejected_reasons.append(f"llm error, fell back to template: {err}")
        else:
            problems = validate_proposal(candidate_proposal, evidence_rows)
            if problems:
                used_fallback = True
                rejected_reasons = problems
            else:
                proposal = candidate_proposal

    if proposal is None:
        proposal = _template_proposal(context, evidence_rows)
        problems = validate_proposal(proposal, evidence_rows)
        if problems:  # template output is contract-breaking by construction — a bug
            raise RuntimeError(f"template proposal failed validation: {problems}")

    draft_id = store.create_draft(conn, Draft(
        prospect_id=prospect_id,
        text=proposal.text,
        evidence_refs=[{"claim": c.claim_text, "evidence_id": c.evidence_id} for c in proposal.claims],
        generator=proposal.generator,
    ))
    return GeneratedDraft(
        draft_id=draft_id,
        prospect_id=prospect_id,
        text=proposal.text,
        claims=proposal.claims,
        generator=proposal.generator,
        used_fallback=used_fallback,
        rejected_reasons=rejected_reasons,
    )
