# Design & Policy — T02+T03 (merged, dated 11 November 2026)

**Status:** Frozen design baseline for implementation. X endpoints referenced here are **documented-available** (docs.x.com, see `docs/x-api-feasibility.md`) but pending console verification — no code calls them until T06/T07 after the user's GO. Sources of truth: `docs/x-api-feasibility.md` (T01), assignment brief, X Automation Rules.

---

## Part A — Policy & consent rules (T02)

### A1. Application invariants (code MUST enforce; not operator-overridable)

| # | Invariant |
|---|---|
| I1 | Every send requires **per-message operator approval** — approval binds to (recipient, draft text) for one send only; no approval carry-over, no batch approval |
| I2 | **Opt-out suppression:** an opted-out recipient can never be sent, regardless of approval or consent state |
| I3 | **Automated/batch sending** (any send not individually approved in the UI at send time) requires a **verified recipient opt-in record**: source, URL/evidence, timestamp, scope, verified-by. Sending is impossible without it |
| I4 | **Dev/test sends** go only to the operator's own accounts or people who explicitly agreed to test — enforced by a test-recipient allowlist |
| I5 | **Volume caps:** ≤ 10 sends per 15 min, ≤ 40 sends per 24 h (inside X's documented 15/15min and 1,440/24h per-user limits) |
| I6 | **Rate-limit respect:** honor `x-rate-limit-*` headers and 429s; exponential backoff; no retry storms; rate-limit hits are surfaced in the UI, not swallowed |
| I7 | **No duplicates:** a send-intent row is persisted *before* the API call; unique constraint on (recipient, active campaign); timeout/ambiguous outcome → status `unknown`, reconcile before any retry — never blind-retry |
| I8 | **Not consent:** following the account, open DM settings, or an old DM thread ≠ consent. OAuth grant of the app ≠ consent to contact |
| I9 | **Secrets hygiene:** credentials live in `.env` (gitignored); never logged, never rendered in UI, never committed |
| I10 | **Evidence-grounded drafting:** every personalized claim in a draft maps to stored evidence; unsupported claims are rejected at generation time |

**Explicit statement:** operator approval authorizes **only one-to-one personalized sends**, never automated bulk unsolicited DMs. This mirrors X's Automation Rules (bulk/unsolicited automated DMs prohibited; automated DMs require prior recipient intent + easy opt-out; following/open-DMs ≠ consent; OAuth grant ≠ consent).

### A2. Consent record (schema)

`consent_records`: `recipient_x_user_id` · `source` (who indicated intent, what they said) · `evidence_url` · `captured_at` · `scope` (what contact it covers) · `verified_by` (operator + time) · `opted_out_at` (nullable). Consent without operator verification = `pending`, not sendable for automated/batch mode.

### A3. Send eligibility rule (single decision function, implemented in T12/T13)

```
send_eligible(recipient, attempt):
  if recipient.opted_out:                                    DENY opted_out            # I2
  if not attempt.approved_by_operator_for_this_message:      DENY unapproved           # I1
  if attempt.mode == "dev_test"
     and recipient not in test_allowlist:                    DENY test_recipient       # I4
  if attempt.mode == "automated_batch"
     and not consent.verified(recipient):                   DENY no_verified_opt_in   # I3
  if sends_15min >= 10 or sends_24h >= 40:                   DENY volume_cap           # I5
  if exists outreach(recipient, status in {intent, sent, unknown}): DENY duplicate     # I7
  if not x_api.available:                                    DENY api_unavailable      # I6/T01
  else: ALLOW
```

Every DENY reason is stored and shown in the UI. A DENY is never silently converted to an ALLOW.

### A4. Allowed vs blocked scenarios

**Allowed:** search public posts; look up public profiles; draft from stored evidence; operator reviews/edits/approves per message; send after eligibility ALLOW to (a) own accounts, (b) consenting testers, (c) discovered prospects (operator-approved, one-to-one, within caps); read own DM events for replies; mark opt-outs.

**Blocked (hard):** bulk/queued unsolicited DMs; automated sends without verified opt-in (I3); sends to opted-out recipients (I2); scraping or browser automation of x.com; unofficial/reverse-engineered endpoints; auto-follow/auto-liking; sending to strangers in dev/test mode; storing or committing credentials.

### A5. Opt-out behavior

Captured two ways: (1) recipient replies with a stop request → visible in reply events → operator marks opted-out (one click, recorded with timestamp); (2) operator adds manually. Opt-out is immediate, permanent, suppresses all future sends (I2), and is shown on the dashboard. Opt-out of *automated* messages is honored before any further automated send, per X rules.

---

## Part B — Architecture (T03)

### B1. Shape: local single-user app

```
Streamlit UI (src/app.py, src/ui/)
        │  operator actions only
        ▼
Service layer (src/services/)
  discovery → evidence → qualification → drafting → consent → outreach(send) → conversations → dashboard
        │                          │
        ▼                          ▼
SQLite (src/db/)            Adapters (src/integrations/)
  prospects                    XClient interface → OfficialXClient (T06/T07) | FakeXClient (tests)
  evidence                     LLMClient interface → TemplateDrafter (default) | API drafter (optional, user-approved only)
  qualification_results
  consent_records
  drafts / outreach_attempts / dm_events
```

One process, one operator, localhost. UI holds no business rules — all policy lives in services; the UI only calls them.

### B2. End-to-end flow (brief's "working" definition)

1. **Discover** (T08): operator enters seed usernames / narrow query → recent search + user lookup → normalized candidates with stable X user IDs + source refs.
2. **Evidence** (T09): posts/profile data persisted with URL, capture time, text → inspectable per candidate.
3. **Qualify** (T09): transparent rule-based score (AI/robotics relevance, role, contribution, freshness) + reasons; missing evidence lowers confidence, never inferred.
4. **Draft** (T10): template-based, claim→evidence mapping enforced (I10); optional LLM path only with user-approved provider (D3 default: none).
5. **Review & consent** (T11/T12): operator inspects evidence, edits draft, approves per message; consent states visible; opt-out controls.
6. **Send** (T13): eligibility check (A3) → persist intent → API call → store `dm_conversation_id`/`dm_event_id`; ambiguous → `unknown`, reconcile.
7. **Track** (T14/T15): reply events linked to outreach records (30-day API window) or manual status path; dashboard shows sent/failed/unknown/replied/attention-needed; values always from DB, never placeholders.

### B3. Frozen interfaces (T06 implements; tests depend on interfaces, not HTTP)

```python
class XClient(Protocol):
    def search_recent_posts(query, max_results=100, next_token=None) -> Page[Post]     # GET /2/tweets/search/recent
    def get_users(user_ids) -> list[Profile]                                           # GET /2/users
    def get_users_by_usernames(usernames) -> list[Profile]                             # GET /2/users/by (added T08 — documented T01 §2 row (b))
    def send_dm(participant_id, text) -> SendResult(dm_conversation_id, dm_event_id)   # POST /2/dm_conversations/with/{id}/messages
    def get_dm_events(participant_id=None, conversation_id=None) -> list[DMEvent]      # GET /2/dm_events family
    # endpoints not entitled in the account raise EndpointUnavailable — never silently simulate success

class LLMClient(Protocol):
    def propose(context, evidence) -> DraftProposal   # claims verified against stored evidence; API impl only with user-approved provider (D3 default: none — template path is in drafting.py)

class Settings(BaseSettings):                     # pydantic-settings, loaded from .env
    x_bearer_token, x_client_id, x_client_secret, oauth_callback_url
    send_cap_15min: int = 10
    send_cap_24h: int = 40
```

### B4. External dependencies (sanctioned list; T04 adds only these as needed)

| Package | For |
|---|---|
| `streamlit` | operator UI |
| `pydantic` + `pydantic-settings` | typed schemas + settings/validation at trust boundaries |
| `httpx` | X API HTTP (OAuth 2.0 PKCE hand-rolled — no SDK dependency) |
| `pytest` | tests |
| stdlib `sqlite3` | persistence (no ORM) |

Everything else requires a new decision record. No scraping libs, no browser automation, no X SDK wrappers.

### B5. Fallbacks (named, from plan §7)

- No approved LLM (current state, D3=A) → `TemplateDrafter`, disclosed in UI/demo/write-up.
- DM send unavailable/not entitled → sending blocked in UI, **escalate immediately** (non-sending build fails the brief's pass gate).
- DM read unavailable → manual reply-status path, clearly labelled.
- Search unavailable → fixture-backed discovery, clearly labelled, no fake live claims.

### B6. Decision records (D1–D5 status, 11 Nov 2026)

- **D1 API access:** CONDITIONAL GO documented in `docs/x-api-feasibility.md`; awaiting user console checklist. Implementation against live endpoints starts T06/T07 only after GO.
- **D2 spend cap:** recommended **$20**; fixed by user at console check.
- **D3 LLM provider:** **RESOLVED → B (13 Nov 2026)**: user-approved free tiers — Groq (`openai/gpt-oss-120b`, 30 req/min, 1K/day) and Mistral presets. Same claim-verification contract as templates; any provider/parse failure falls back to the deterministic template automatically. Keys optional in `.env` (GROQ_API_KEY / MISTRAL_API_KEY).
- **D4 reply monitoring:** MUST tier = manual status path; automated via `dm.read` once console confirms scope.
- **D5 hosting:** A — local source + <15-min setup (brief allows this explicitly).

### B7. Non-goals (unchanged from plan §2)

No multi-tenant SaaS, cloud deploy, team roles, billing, queues/streams/vector DBs, mass crawling, autonomous sending, or follow-up sequences.
