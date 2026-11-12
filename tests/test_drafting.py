import json

import pytest

from src.db import connect, init_db, store
from src.integrations.llm_client import ClaimRef, DraftProposal, FakeLLMClient
from src.services.drafting import (
    SNIPPET_LIMIT,
    NoGroundedEvidenceError,
    generate_draft,
)


@pytest.fixture
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def _seed_prospect_with_evidence(conn, bio="Founder building humanoid robots. ex-PhD researcher",
                                 post_text="released our new ML perception model, open source on GitHub",
                                 post_created="2026-11-10T00:00:00Z"):
    from src.models import Prospect
    pid = store.upsert_prospect(conn, Prospect(
        x_user_id="100", username="robo", display_name="Robo", source="seed"))
    ev_ids = []
    from src.models import Evidence
    ev_ids.append(store.upsert_evidence(conn, Evidence(
        prospect_id=pid, url="https://x.com/robo", source_type="profile", text=bio)))
    if post_text:
        ev_ids.append(store.upsert_evidence(conn, Evidence(
            prospect_id=pid, url="https://x.com/robo/status/p1", source_type="post",
            text=post_text)))
    return pid, ev_ids


# --- deterministic template path ---------------------------------------------

def test_template_draft_is_grounded_and_persisted(conn):
    pid, ev_ids = _seed_prospect_with_evidence(conn)
    draft = generate_draft(conn, pid)

    assert draft.generator == "template"
    assert not draft.used_fallback
    assert len(draft.claims) == 2  # profile bio + one recent post
    claim_by_evidence = {c.evidence_id: c.claim_text for c in draft.claims}
    assert set(claim_by_evidence) == set(ev_ids)

    # every claim is a verbatim snippet of its evidence AND appears in the draft text
    evidence_map = {r["id"]: r["text"] for r in store.get_evidence_for_prospect(conn, pid)}
    for c in draft.claims:
        assert c.claim_text in evidence_map[c.evidence_id]
        assert c.claim_text in draft.text

    # purpose sentence is fund context, greeting uses the display name
    assert "Southeast Asia" in draft.text
    assert "Hi Robo," in draft.text
    assert "robotics and embodied AI" in draft.text  # domain from matched terms

    # persisted with evidence refs for the UI's editable review (T12)
    row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft.draft_id,)).fetchone()
    refs = json.loads(row["evidence_refs"])
    assert {r["evidence_id"] for r in refs} == set(ev_ids)
    assert row["generator"] == "template" and row["status"] == "draft"


def test_template_snippet_is_word_bounded_and_verbatim(conn):
    long_bio = "robot " * 40 + "."
    pid, _ = _seed_prospect_with_evidence(conn, bio=long_bio.strip(), post_text=None)
    draft = generate_draft(conn, pid)
    claim = draft.claims[0]
    assert len(claim.claim_text) <= SNIPPET_LIMIT
    assert claim.claim_text in long_bio.strip()  # verbatim, no ellipsis fabrication


def test_drafting_without_evidence_raises(conn):
    from src.models import Prospect
    pid = store.upsert_prospect(conn, Prospect(
        x_user_id="999", username="ghost", source="seed"))
    with pytest.raises(NoGroundedEvidenceError):
        generate_draft(conn, pid)


# --- LLM path (protocol + fake; real client only after D3 approval) ----------

def test_llm_path_accepts_grounded_proposal(conn):
    pid, ev_ids = _seed_prospect_with_evidence(conn)
    evidence_map = {r["id"]: r["text"] for r in store.get_evidence_for_prospect(conn, pid)}
    snippet = evidence_map[ev_ids[1]][:60]
    fake = FakeLLMClient(proposals=[DraftProposal(
        text=(f"Hi Robo,\n\n\"{snippet}\" — is that still the focus? "
              "We speak with builders across Southeast Asia."),
        claims=[ClaimRef(evidence_id=ev_ids[1], claim_text=snippet)],
        generator="llm:fake",
    )])
    draft = generate_draft(conn, pid, llm=fake)

    assert draft.generator == "llm:fake" and not draft.used_fallback
    assert draft.claims[0].evidence_id == ev_ids[1]
    assert fake.calls[0]["context"]["x_user_id"] == "100"  # generator received only context + stored evidence


def test_llm_proposal_with_unknown_evidence_is_rejected_falls_back(conn):
    pid, _ = _seed_prospect_with_evidence(conn)
    fake = FakeLLMClient(proposals=[DraftProposal(
        text="Hi Robo, yourquantum chips work is impressive.",  # claim not even included
        claims=[ClaimRef(evidence_id=999, claim_text="quantum chips work")],
        generator="llm:fake",
    )])
    draft = generate_draft(conn, pid, llm=fake)

    assert draft.used_fallback and draft.generator == "template"
    assert any("unknown evidence" in r for r in draft.rejected_reasons)
    assert draft.text.startswith("Hi Robo,")  # deterministic path produced the draft


def test_llm_claim_not_present_in_text_is_rejected(conn):
    pid, ev_ids = _seed_prospect_with_evidence(conn)
    evidence_map = {r["id"]: r["text"] for r in store.get_evidence_for_prospect(conn, pid)}
    snippet = evidence_map[ev_ids[0]][:40]
    fake = FakeLLMClient(proposals=[DraftProposal(
        text="Hi Robo, would you be open to a chat?",  # claim text nowhere in the draft
        claims=[ClaimRef(evidence_id=ev_ids[0], claim_text=snippet)],
        generator="llm:fake",
    )])
    draft = generate_draft(conn, pid, llm=fake)
    assert draft.used_fallback
    assert any("does not appear" in r for r in draft.rejected_reasons)


def test_llm_fabricated_familiarity_is_rejected(conn):
    pid, ev_ids = _seed_prospect_with_evidence(conn)
    evidence_map = {r["id"]: r["text"] for r in store.get_evidence_for_prospect(conn, pid)}
    snippet = evidence_map[ev_ids[1]][:40]
    fake = FakeLLMClient(proposals=[DraftProposal(
        text=(f"Great meeting you! As we discussed, \"{snippet}\". Let's continue."),
        claims=[ClaimRef(evidence_id=ev_ids[1], claim_text=snippet)],
        generator="llm:fake",
    )])
    draft = generate_draft(conn, pid, llm=fake)
    assert draft.used_fallback
    assert any("fabricated-familiarity" in r for r in draft.rejected_reasons)


def test_llm_zero_claims_despite_evidence_is_rejected(conn):
    pid, _ = _seed_prospect_with_evidence(conn)
    fake = FakeLLMClient(proposals=[DraftProposal(
        text="Hi Robo, would you be open to a short conversation?",
        claims=[],
        generator="llm:fake",
    )])
    draft = generate_draft(conn, pid, llm=fake)
    assert draft.used_fallback
    assert any("personalisation is required" in r for r in draft.rejected_reasons)


def test_llm_error_falls_back_to_template(conn):
    pid, _ = _seed_prospect_with_evidence(conn)
    fake = FakeLLMClient()
    fake.fail_next(RuntimeError("provider outage"))
    draft = generate_draft(conn, pid, llm=fake)
    assert draft.generator == "template" and draft.used_fallback
    assert any("provider outage" in r for r in draft.rejected_reasons)


def test_unknown_prospect_raises(conn):
    with pytest.raises(ValueError):
        generate_draft(conn, 4242)
