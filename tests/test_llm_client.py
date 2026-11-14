"""AI drafting path (D3=B): OpenAI-compatible client against Groq/Mistral — all
unit tests run on httpx.MockTransport; the live Groq test is opt-in (-m live) and
free-tier. Every proposal still passes the drafting service's claim contract."""

import json

import httpx
import pytest

from src.config import Settings
from src.db import connect, init_db, store
from src.integrations.llm_client import (
    CandidateContext,
    EvidenceBundle,
    LLMError,
    OpenAICompatLLMClient,
    make_groq_client,
)
from src.services.drafting import generate_draft

CTX = CandidateContext(x_user_id="100", username="robo", display_name="Robo")


def _evidence() -> list[EvidenceBundle]:
    return [
        EvidenceBundle(evidence_id=1, url="https://x.com/robo", source_type="profile",
                       text="Founder building humanoid robots. ex-PhD researcher"),
        EvidenceBundle(evidence_id=2, url="https://x.com/robo/status/p1", source_type="post",
                       text="released our new ML perception model, open source on GitHub"),
    ]


def _client(content: str, status: int = 200) -> OpenAICompatLLMClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.groq.com"
        assert request.headers["Authorization"].startswith("Bearer ")
        body = json.loads(request.content)
        assert body["model"] == "openai/gpt-oss-120b"
        return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})

    return make_groq_client("fake-key", transport=httpx.MockTransport(handler))


def _good_content() -> str:
    return json.dumps({
        "text": 'Hi Robo,\n\nI came across your profile — "Founder building humanoid '
                'robots. ex-PhD researcher" — and your post about the "released our new '
                'ML perception model" stood out. We build an AI ecosystem across '
                "Southeast Asia; open to a short conversation?",
        "claims": [
            {"evidence_id": 1, "claim_text": "Founder building humanoid robots"},
            {"evidence_id": 2, "claim_text": "released our new ML perception model"},
        ],
    })


# --- client parsing / transport errors ---------------------------------------

def test_valid_json_becomes_proposal():
    proposal = _client(_good_content()).propose(CTX, _evidence())
    assert proposal.text.startswith("Hi Robo")
    assert proposal.generator == "llm:groq/openai/gpt-oss-120b"
    assert {c.evidence_id for c in proposal.claims} == {1, 2}


def test_fenced_json_is_stripped():
    fenced = "```json\n" + _good_content() + "\n```"
    proposal = _client(fenced).propose(CTX, _evidence())
    assert proposal.claims  # fence stripping worked


def test_prose_around_json_is_tolerated():
    wrapped = "Here is your draft:\n" + _good_content() + "\nHope that helps!"
    assert _client(wrapped).propose(CTX, _evidence()).claims


def test_missing_text_rejected():
    with pytest.raises(LLMError, match="claim contract"):
        _client(json.dumps({"claims": []})).propose(CTX, _evidence())


def test_no_json_rejected():
    with pytest.raises(LLMError, match="no JSON object"):
        _client("I will not produce JSON today.").propose(CTX, _evidence())


def test_http_error_maps_to_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    with pytest.raises(LLMError, match="429"):
        _client("", status=429).propose(CTX, _evidence())  # handler ignores status arg


def test_timeout_maps_to_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    client = OpenAICompatLLMClient(
        name="groq/test", base_url="https://api.groq.com/openai/v1",
        api_key="fake-key", model="openai/gpt-oss-120b",
        transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError, match="timeout"):
        client.propose(CTX, _evidence())


# --- service integration: accepted proposal wins, rejected one falls back -----

def _seed_prospect_with_evidence(conn):
    from src.models import Evidence, Prospect
    pid = store.upsert_prospect(conn, Prospect(
        x_user_id="100", username="robo", display_name="Robo", source="seed"))
    store.upsert_evidence(conn, Evidence(
        prospect_id=pid, url="https://x.com/robo", source_type="profile",
        text="Founder building humanoid robots. ex-PhD researcher"))
    store.upsert_evidence(conn, Evidence(
        prospect_id=pid, url="https://x.com/robo/status/p1", source_type="post",
        text="released our new ML perception model, open source on GitHub"))
    return pid


def test_service_uses_grounded_llm_proposal():
    conn = connect(":memory:")
    init_db(conn)
    pid = _seed_prospect_with_evidence(conn)
    client = _client(_good_content())
    draft = generate_draft(conn, pid, llm=client)
    assert draft.generator == "llm:groq/openai/gpt-oss-120b"
    assert not draft.used_fallback
    row = conn.execute("SELECT generator FROM drafts WHERE id = ?", (draft.draft_id,)).fetchone()
    assert row["generator"] == "llm:groq/openai/gpt-oss-120b"


def test_service_falls_back_when_llm_hallucinates():
    conn = connect(":memory:")
    init_db(conn)
    pid = _seed_prospect_with_evidence(conn)
    hallucinated = json.dumps({
        "text": "Hi Robo, your $50M Series B is impressive!",
        "claims": [{"evidence_id": 999, "claim_text": "$50M Series B"}],  # invented evidence
    })
    draft = generate_draft(conn, pid, llm=_client(hallucinated))
    assert draft.used_fallback and draft.generator == "template"
    assert any("unknown evidence" in r for r in draft.rejected_reasons)


# --- provider selection -------------------------------------------------------

def test_provider_selection_honours_keys():
    settings = Settings(_env_file=None, groq_api_key="g", mistral_api_key="m")
    assert workflows_llm_client_for(settings, "groq") is not None
    assert workflows_llm_client_for(settings, "mistral") is not None
    assert workflows_llm_client_for(settings, "template") is None
    assert workflows_llm_client_for(Settings(_env_file=None), "groq") is None
    assert workflows_llm_providers(Settings(_env_file=None, groq_api_key="g")) == ["template", "groq"]


def workflows_llm_client_for(settings, provider):
    from src.ui.workflows import llm_client_for
    return llm_client_for(settings, provider)


def workflows_llm_providers(settings):
    from src.ui.workflows import llm_providers
    return llm_providers(settings)


# --- live (opt-in, free tier) --------------------------------------------------

@pytest.mark.live
def test_live_groq_proposal_is_grounded():
    from src.config import get_settings

    settings = get_settings()  # reads .env — Settings(_env_file=None) would ignore it
    if not settings.groq_api_key:
        pytest.skip("no GROQ_API_KEY in .env")
    proposal = make_groq_client(settings.groq_api_key).propose(CTX, _evidence())
    assert proposal.text.strip()
    assert proposal.claims  # the model was asked for claim refs


@pytest.mark.live
def test_live_mistral_proposal_is_grounded():
    from src.config import get_settings

    settings = get_settings()  # reads .env — Settings(_env_file=None) would ignore it
    if not settings.mistral_api_key:
        pytest.skip("no MISTRAL_API_KEY in .env")
    from src.integrations.llm_client import LLMError, make_mistral_client

    try:
        proposal = make_mistral_client(settings.mistral_api_key).propose(CTX, _evidence())
    except LLMError as err:
        if "429" in str(err):
            pytest.skip(f"mistral free tier rate-limited right now ({err}) — key itself is valid")
        raise
    assert proposal.text.strip()
    assert proposal.claims
