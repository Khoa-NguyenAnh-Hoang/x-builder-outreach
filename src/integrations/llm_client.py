"""LLM boundary (T10).

Any draft generator — template or model — must return a DraftProposal whose
personalized claims each reference stored evidence and appear verbatim in the
draft text; the drafting service verifies this contract for every path.

No API-backed LLMClient exists: the approved provider default is D3=A
(deterministic templates). An API implementation is only built after explicit
user approval of provider, cost, and terms — never silently.
"""

import json
import re
from typing import Protocol

import httpx
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


# --- real providers (D3=B, user-approved free tiers) ------------------------------

class LLMError(Exception):
    """Any provider/parse failure — the drafting service falls back to the template."""


SYSTEM_PROMPT = (
    "You draft short, warm, personalised outreach DMs for an AI/robotics venture fund. "
    "Ground every personalisation in the numbered evidence provided. "
    'Respond with strict JSON only: {"text": string, "claims": '
    '[{"evidence_id": int, "claim_text": string}]}. '
    "Each claim_text must be an exact contiguous snippet copied from the evidence item "
    "with that id and must appear word-for-word in text. Never invent facts, achievements, "
    "metrics, or shared history. No markdown, no code fences."
)

USER_INSTRUCTIONS = (
    "Write 2-4 sentences: greet the candidate, reference one or two evidence snippets "
    "verbatim (those are your claims), mention that we build an AI ecosystem across "
    "Southeast Asia and invite a short conversation."
)


class OpenAICompatLLMClient:
    """Works with any OpenAI-compatible chat API (Groq, Mistral, ...). Output is a
    DraftProposal — the drafting service's claim contract still verifies it, so a
    hallucinated claim can never reach a draft."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str,
                 transport: httpx.BaseTransport | None = None):
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._transport = transport
        self.calls: list[dict] = []

    def propose(self, context: CandidateContext, evidence: list[EvidenceBundle]) -> DraftProposal:
        self.calls.append({"context": context.model_dump(), "n_evidence": len(evidence)})
        bundles = [e for e in evidence if e.text]
        lines = "\n".join(f"[{b.evidence_id}] ({b.source_type}) {b.text.strip()}" for b in bundles)
        who = context.display_name or (f"@{context.username}" if context.username else "there")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Candidate: {who}\n\nEvidence:\n{lines}\n\n{USER_INSTRUCTIONS}"},
        ]
        try:
            with httpx.Client(timeout=30, transport=self._transport) as client:
                resp = client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "messages": messages,
                          "temperature": 0.7, "max_tokens": 600},
                )
        except httpx.TimeoutException as err:
            raise LLMError(f"{self.name} timeout: {err}") from err
        except httpx.HTTPError as err:
            raise LLMError(f"{self.name} unreachable: {err}") from err
        if resp.status_code != 200:
            raise LLMError(f"{self.name} error {resp.status_code}: {resp.text[:160]}")
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as err:
            raise LLMError(f"{self.name} response shape unexpected: {err}") from err
        text, claims = self._parse(content)
        return DraftProposal(text=text, claims=claims, generator=f"llm:{self.name}")

    @staticmethod
    def _parse(content: str) -> tuple[str, list[ClaimRef]]:
        s = content.strip()
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.DOTALL).strip()
        start, end = s.find("{"), s.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("no JSON object found in model output")
        try:
            payload = json.loads(s[start:end + 1])
            text = payload["text"]
            if not isinstance(text, str) or not text.strip():
                raise KeyError("text")
            claims = [ClaimRef(evidence_id=int(c["evidence_id"]),
                               claim_text=str(c["claim_text"]))
                      for c in payload.get("claims", [])]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
            raise LLMError(f"model output did not follow the claim contract: {err}") from err
        return text, claims


def make_groq_client(api_key: str, model: str = "openai/gpt-oss-120b",
                     transport: httpx.BaseTransport | None = None) -> OpenAICompatLLMClient:
    """Groq free tier (user-approved): strongest free generator, 30 req/min / 1K/day."""
    return OpenAICompatLLMClient(name=f"groq/{model}", base_url="https://api.groq.com/openai/v1",
                                 api_key=api_key, model=model, transport=transport)


def make_mistral_client(api_key: str, model: str = "mistral-small-latest",
                        transport: httpx.BaseTransport | None = None) -> OpenAICompatLLMClient:
    return OpenAICompatLLMClient(name=f"mistral/{model}", base_url="https://api.mistral.ai/v1",
                                 api_key=api_key, model=model, transport=transport)
