"""Typed records for the rows persisted in src/db (validation at construction)."""

from pydantic import BaseModel


class Prospect(BaseModel):
    x_user_id: str
    username: str | None = None
    display_name: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    source: str  # seed | search | manual
    source_query: str | None = None


class Evidence(BaseModel):
    prospect_id: int
    url: str
    source_type: str  # post | profile | bio_link
    text: str | None = None


class Qualification(BaseModel):
    prospect_id: int
    score: float
    components: dict[str, float]
    reasons: list[str]
    confidence: str  # high | medium | low


class ConsentRecord(BaseModel):
    prospect_id: int
    source: str
    evidence_url: str | None = None
    scope: str
    verified_by: str | None = None
    verified_at: str | None = None
    opted_out_at: str | None = None


class Draft(BaseModel):
    prospect_id: int
    text: str
    evidence_refs: list[dict]  # [{claim, evidence_id}]
    generator: str  # template | llm:<name>


class DMEvent(BaseModel):
    x_dm_event_id: str
    prospect_id: int | None = None
    outreach_attempt_id: int | None = None
    conversation_id: str | None = None
    event_type: str  # MessageCreate | ParticipantsJoin | ParticipantsLeave
    sender_x_user_id: str | None = None
    text: str | None = None
    occurred_at: str | None = None
