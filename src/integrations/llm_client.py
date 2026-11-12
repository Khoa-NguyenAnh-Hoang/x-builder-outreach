"""LLM boundary (T10).

Any draft generator — template or model — must return a DraftProposal whose
personalized claims each reference stored evidence and appear verbatim in the
draft text; the drafting service verifies this contract for every path.

No API-backed LLMClient exists: the approved provider default is D3=A
(deterministic templates). An API implementation is only built after explicit
user approval of provider, cost, and terms — never silently.
"""

from typing import Protocol

from pydantic import BaseModel


class CandidateContext(BaseModel):
    x_user_id: str
    username: str | None = None
    display_name: str | None = None


class EvidenceBundle(BaseModel):
    evidence_id: int
    url: str
    source_type: str  # post | profile
    text: str | None = None


class ClaimRef(BaseModel):
    """One personalized claim, anchored to the evidence it is grounded in."""

    evidence_id: int
    claim_text: str  # verbatim snippet from that evidence item


class DraftProposal(BaseModel):
    text: str
    claims: list[ClaimRef] = []
    generator: str  # "template" | "llm:<name>"


class LLMClient(Protocol):
    """A model-backed generator, only ever wired in with user approval (D3)."""

    name: str

    def propose(self, context: CandidateContext, evidence: list[EvidenceBundle]) -> DraftProposal: ...


class FakeLLMClient:
    """Deterministic test double for the LLM path: canned proposals, one-shot errors."""

    def __init__(self, proposals: list[DraftProposal] | None = None, name: str = "fake-llm"):
        self._proposals = list(proposals or [])
        self._errors: list[Exception] = []
        self.name = name
        self.calls: list[dict] = []

    def fail_next(self, error: Exception) -> None:
        self._errors.append(error)

    def propose(self, context: CandidateContext, evidence: list[EvidenceBundle]) -> DraftProposal:
        self.calls.append({"context": context.model_dump(), "n_evidence": len(evidence)})
        if self._errors:
            raise self._errors.pop(0)
        if self._proposals:
            return self._proposals.pop(0)
        with_text = [e for e in evidence if e.text]
        if not with_text:
            return DraftProposal(
                text=(f"Hi {context.display_name or context.username or 'there'}, "
                      "would you be open to a short conversation?"),
                claims=[],
                generator=f"llm:{self.name}",
            )
        first = with_text[0]
        snippet = first.text.strip()[:80]
        greeting = context.display_name or (
            f"@{context.username}" if context.username else "there"
        )
        return DraftProposal(
            text=(f"Hi {greeting},\n\n\"{snippet}\" caught my eye. "
                  "Would you be open to a short conversation?"),
            claims=[ClaimRef(evidence_id=first.evidence_id, claim_text=snippet)],
            generator=f"llm:{self.name}",
        )
