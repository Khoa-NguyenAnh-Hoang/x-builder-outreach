"""T09 (part 2) — transparent rule-based qualification score.

Components (each 0..1), weights exposed, every reason cites what matched and where.
Pure `qualify()` is deterministic — same evidence always yields the same score.
Missing evidence lowers confidence and is reported as unknown; nothing is inferred.
"""

import re
import sqlite3
from datetime import datetime, timezone

from src.db import store
from src.integrations.x_client import Post, Profile
from src.models import Qualification

WEIGHTS = {"relevance": 0.40, "role": 0.25, "contribution": 0.20, "freshness": 0.15}

AI_TERMS = [
    "ai", "artificial intelligence", "machine learning", "deep learning", "neural",
    "llm", "llms", "gpt", "genai", "gen ai", "transformer", "agentic", "agents",
    "rag", "fine-tuning", "diffusion",
]
ROBOTICS_TERMS = [
    "robot", "robots", "robotics", "humanoid", "humanoids", "embodied", "drone",
    "drones", "actuator", "perception", "slam", "manipulation", "autonomous vehicle",
    "self-driving",
]
ROLE_TERMS = [
    "founder", "co-founder", "ceo", "cto", "building", "researcher", "research",
    "phd", "professor", "engineer", "developer", "scientist",
]
TECH_TERMS = [
    "github", "arxiv", "paper", "open source", "open-source", "shipped", "launched",
    "launching", "release", "released", "demo", "prototype", "api", "sdk",
    "benchmark", "dataset",
]


def _matches(text: str, terms: list[str]) -> list[str]:
    """Distinct matched terms (word-boundary match, case-insensitive)."""
    lowered = text.lower()
    return [t for t in terms if re.search(rf"\b{re.escape(t)}\b", lowered)]


def _freshness(posts: list[Post]) -> tuple[float, str]:
    created = [p.created_at for p in posts if p.created_at]
    if not created:
        # Unknown is not scored: freshness of nothing is 0, never a guess.
        return 0.0, "no dated post evidence — freshness unknown (not inferred)"
    newest = max(datetime.fromisoformat(c.replace("Z", "+00:00")) for c in created)
    age_days = (datetime.now(timezone.utc) - newest).days
    if age_days <= 7:
        return 1.0, f"newest post is {age_days}d old"
    if age_days <= 30:
        return 0.7, f"newest post is {age_days}d old"
    if age_days <= 90:
        return 0.4, f"newest post is {age_days}d old — getting stale"
    return 0.1, f"newest post is {age_days}d old — stale"


def qualify(prospect_id: int, profile: Profile | None, posts: list[Post]) -> Qualification:
    bio_text = " ".join(
        v for v in ((profile.name or "") if profile else "",
                    (profile.description or "") if profile else "")
    ).strip()
    post_text = " ".join(p.text for p in posts)

    ai_hits = _matches(bio_text, AI_TERMS) + _matches(post_text, AI_TERMS)
    robotics_hits = _matches(bio_text, ROBOTICS_TERMS) + _matches(post_text, ROBOTICS_TERMS)
    role_hits = _matches(bio_text, ROLE_TERMS) + _matches(post_text, ROLE_TERMS)
    tech_hits = _matches(bio_text, TECH_TERMS) + _matches(post_text, TECH_TERMS)

    reasons: list[str] = []
    relevance = min(1.0, (len(ai_hits) + len(robotics_hits)) / 3)
    if ai_hits:
        reasons.append(f"AI/ML relevance: matched {sorted(set(ai_hits))}")
    if robotics_hits:
        reasons.append(f"robotics relevance: matched {sorted(set(robotics_hits))}")
    if not ai_hits and not robotics_hits:
        reasons.append("no AI/robotics signals in captured evidence")

    role = min(1.0, len(role_hits) / 2)
    if role_hits:
        reasons.append(f"builder/researcher role signals: {sorted(set(role_hits))}")

    contribution = min(1.0, len(tech_hits) / 2)
    if tech_hits:
        reasons.append(f"technical contribution signals: {sorted(set(tech_hits))}")

    freshness, freshness_reason = _freshness(posts)
    reasons.append(f"freshness: {freshness_reason}")

    n_posts = len(posts)
    has_profile = profile is not None and bool(bio_text)
    if not has_profile and n_posts == 0:
        confidence = "low"
        reasons.append("insufficient evidence: no profile or post text captured — "
                       "score is zero by absence, not by inference")
    elif n_posts == 0:
        confidence = "low"
        reasons.append("profile-only evidence — recent posts not captured, confidence limited")
    elif n_posts == 1:
        confidence = "medium"
    else:
        confidence = "high"

    score = (
        WEIGHTS["relevance"] * relevance
        + WEIGHTS["role"] * role
        + WEIGHTS["contribution"] * contribution
        + WEIGHTS["freshness"] * freshness
    )
    return Qualification(
        prospect_id=prospect_id,
        score=round(score, 4),
        components={
            "relevance": round(relevance, 4),
            "role": round(role, 4),
            "contribution": round(contribution, 4),
            "freshness": round(freshness, 4),
        },
        reasons=reasons,
        confidence=confidence,
    )


def qualify_and_persist(conn: sqlite3.Connection, prospect_id: int,
                        profile: Profile | None, posts: list[Post]) -> Qualification:
    qualification = qualify(prospect_id, profile, posts)
    store.save_qualification(conn, qualification)
    return qualification
