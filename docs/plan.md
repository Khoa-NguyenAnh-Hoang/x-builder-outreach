# Plan: GenAI Fund — X Builder Discovery & Consent-Based Outreach Prototype

## 1. Context recap

- Build a usable prototype for GenAI Fund to discover AI/robotics builders on X, qualify them with verifiable evidence, prepare personalized outreach drafts, and track approved outreach and replies.
- The assignment requires working software, a 3–5 minute end-to-end demo, and a one-page write-up. Submission deadline: **Tuesday, 17 November 2026, 12:00 PM GMT+7**; participation confirmation deadline: **Friday, 13 November 2026, 12:00 PM GMT+7**.
- Repository is greenfield and will be created later. Target coding agent: **OpenCode**. Foundation: **Python 3.12 + `uv`**, local machine, CPU-only.
- Budget default is **$0 until T01 completes**. On a T01 GO, a user-approved, hard-capped small X API budget (amount fixed at GO) may be spent on confirmed pay-per-use prices; no spend happens before T01 documents pricing. No paid LLM (If needed I will subscribe to Command Code 1 dollar Go Plan) or hosting spend is authorized by this plan.
- Hard compliance boundary: no unsolicited automated or bulk DMs. Every send requires per-message operator approval. Recipient opt-in is required for automated/batch sending and for all development/test sends (own or consenting accounts only); the fund may send operator-approved, personalized one-to-one DMs to discovered prospects, with opt-out suppression, volume caps, and rate-limit respect.

## 2. Scope boundary

### In scope

- A small local web application that an operator can run independently.
- Discovery from seed accounts and/or narrow keyword searches using only authorized, currently available X API endpoints.
- Candidate profiles with source evidence, evidence timestamps/URLs, qualification score, and a concise reason for fit.
- Evidence-grounded personalized DM drafts for human review; drafts must not assert facts unsupported by stored evidence.
- Per-message operator approval on every send, opt-out suppression, recipient-consent records for automated/batch and test sends, and a hard send eligibility check.
- Sending only through an authorized official API path; development/test sends go only to the operator's own/test accounts or people who have explicitly agreed to test.
- Duplicate prevention, persistent outreach status, error handling, and reply visibility where authorized API access supports it.
- Local SQLite persistence, automated tests, setup documentation, demo recording, and one-page write-up.

### Out of scope

- Cold automated DM outreach to discovered prospects, bulk unsolicited messaging, or automated follow-up sequences.
- Browser automation, scraping the X website, unofficial session-cookie automation, reverse-engineered endpoints, or bypassing API limits/access controls.
- Multi-tenant SaaS, production cloud deployment, team roles, billing, analytics warehouse, Kafka, Spark, Airflow, vector database, or large-scale crawling.
- Autonomous sending without a human approval step.
- Claims of fully automated reply monitoring if the approved X API permissions/endpoints do not support it.
- Any paid API or model subscription without explicit user approval.

## 3. Deliverable checklist mapped to tasks

| Assignment deliverable                                                                                     | Tasks              |
| ---------------------------------------------------------------------------------------------------------- | ------------------ |
| Working prototype: discovery → qualification → evidence → draft → approval → eligible test send → tracking | T01–T16            |
| Usable setup under 15 minutes; requirements and account/API needs disclosed                                | T00, T17           |
| No duplicate messages; safe handling of ambiguous send outcomes                                            | T09, T13, T14, T16 |
| Evidence-based personalization and fit explanations                                                        | T08–T12            |
| 3–5 minute end-to-end demo video, including limitations                                                    | T18                |
| One-page write-up: approach, trade-offs, next steps, costs, AI-tool use, verification                      | T19                |
| Submission package and final deadline check                                                                | T20                |

## 4. Ordered implementation tasks

> Estimates are focused engineering time, not calendar duration. Keep each task within two hours; split a task rather than allowing the agent to expand it. Do not start implementation against X until T01 has a documented GO decision.

#### Priority tiers (set 11 Nov 2026 — user commits ~30 h/week ≈ 23.6 h before the deadline; original estimates total 31.0 h)

Tier budgets override the per-task estimates below when executing. MUST must fit the calendar; SHOULD runs only if slack appears; DEFER is dropped without replacement.

- **MUST — ≈ 23.0 h total:** T00 0.5 · T01 1.5 · T02+T03 merged into one design/policy doc 1.5 · T04 1.0 · T05 1.5 · T06 1.0 · T07 1.0 · T08 1.5 · T09 1.0 · T10 1.5 · T11 core 1.5 · T12 1.0 · T13 1.5 · T14 manual-status path only 0.5 · T15 core, no filters 1.0 · T16 core suite 1.0 · T17 1.0 · T18 1.5 · T19 1.0 · T20 1.0. (T-CONF is manual overhead, not counted.)
- **SHOULD (only with slack):** T14 automated reply tracking via confirmed DM read endpoints (+1.0) · T15 status filters (+0.5) · T06 fuller failure-mode fake-client tests (+0.5) · T10 approved-LLM draft path (+0.5) · T16 extended test breadth (+1.0).
- **DEFER (no replacement):** UI polish, dashboard filters beyond status, docs beyond one design/policy file, test breadth beyond the MUST core.

### T-CONF — Confirm participation (manual, time-critical)

- **Action:** Email `hr@genaifund.ai` confirming participation in the assignment (brief requirement, "Confirm participation"). This is the user's manual action, not agent work.
- **Depends on:** None
- **Acceptance check:** Confirmation email sent before **Friday 13 November 2026, 12:00 PM (GMT+7)**.
- **Estimate:** 0.1 h (calendar action, outside agent estimates)

### T00 — Create the greenfield repository foundation

- **Action:** Initialize the repository and minimal Python project using Python 3.12 and `uv`; add a concise README and standard ignore rules.
- **Files:** `pyproject.toml`, `README.md`, `.gitignore`, `.python-version`
- **Depends on:** None
- **Acceptance check:** `uv python pin 3.12`, `uv sync`, and `uv run python --version` succeed; version output is Python 3.12.x; `git status` is clean after the initial commit.
- **Estimate:** 1.0 h
- **Risk:** Low. Do not add dependencies before their need is established.

### T01 — Verify official X API feasibility and actual spend

- **Action:** In the X Developer Console and current official documentation, verify whether the account/app can access (a) public post search, (b) user/profile lookup, (c) authorized account authentication, (d) sending DMs, and (e) reading DM events/conversations. Record the exact product, endpoint, permission, authentication flow, rate limit, and current price for each. Run only harmless read/auth checks; do not send a message yet.
- **Files:** `docs/x-api-feasibility.md`
- **Depends on:** None
- **Acceptance check:** The document contains a dated endpoint/access matrix with evidence links and a clear GO/NO-GO for discovery, sending, and reply tracking. No endpoint is marked available based only on an old tutorial or third-party API wrapper.
- **Estimate:** 1.5 h
- **Risk:** **Critical.** If official API access is unavailable or unaffordable, the assignment's actual-send requirement may be blocked. Stop and report the blocker; never replace it with scraping or browser automation.

### T02 — Freeze the policy and consent rules

- **Action:** Translate current X Automation Rules and the assignment's test-account restrictions into explicit application invariants. Every send requires per-message operator approval; recipient opt-in is required before automated/batch sending and for all dev/test sends; record the consent source, timestamp, scope, and operator verification. Following the account or having an open DM inbox is not consent.
- **Files:** `docs/design-and-policy.md` (merged with T03 per the MUST tier)
- **Depends on:** T01
- **Acceptance check:** The document defines allowed test scenarios, blocked scenarios, opt-out behavior, volume caps, and a send eligibility rule. It explicitly states that operator approval authorizes only one-to-one personalized sends, never automated bulk unsolicited DMs.
- **Estimate:** 1.0 h
- **Risk:** High. Policy interpretation is a product constraint, not a feature that can be relaxed to satisfy the demo.

### T03 — Choose the smallest architecture and freeze interfaces

- **Action:** Define a local single-user architecture: Streamlit UI, application/service layer, SQLite persistence, typed schemas, official-X client adapter, and an optional LLM adapter. Keep external integrations behind interfaces. Use deterministic qualification/draft fallback if no approved LLM provider is available.
- **Files:** `docs/design-and-policy.md` (merged with T02; decision records go in the same file per the MUST tier)
- **Depends on:** T01, T02
- **Acceptance check:** Architecture diagram or text flow covers discovery, evidence, qualification, consent, draft, approval, send, and tracking. Every external dependency and fallback is named. No unverified API endpoint is presented as implemented.
- **Estimate:** 1.0 h
- **Risk:** Medium. Avoid overengineering or adding distributed infrastructure.

### T04 — Create application skeleton and configuration handling

- **Action:** Create the package layout, typed settings, environment-variable loading, structured logging, and a safe example environment file. Keep secrets out of source control and UI logs.
- **Files:** `src/`, `src/app.py`, `src/config.py`, `src/logging_config.py`, `.env.example`, `.gitignore`, `pyproject.toml`
- **Depends on:** T00, T03
- **Acceptance check:** `uv run python -m compileall src` succeeds; missing required configuration produces a clear actionable error; `.env` and credential files are ignored by Git.
- **Estimate:** 1.5 h
- **Risk:** Low–Medium. Use only dependencies justified by the selected architecture.

### T05 — Implement the minimal persistent data model

- **Action:** Define and initialize SQLite tables for prospects, evidence, qualification results, consent records, drafts, outreach attempts, and conversation/reply events. Add uniqueness constraints for X user IDs and outreach deduplication.
- **Files:** `src/db/`, `src/models/`, `tests/test_db.py`
- **Depends on:** T03, T04
- **Acceptance check:** Database initialization is repeatable; foreign keys and uniqueness constraints are enforced; tests cover create/read/update and duplicate prospect/outreach insertion.
- **Estimate:** 1.5 h
- **Risk:** Medium. Keep schema small and migrations or schema versioning explicit.

### T06 — Implement X client boundary and test doubles

- **Action:** Define typed interfaces for search, user lookup, DM send, and authorized conversation/event retrieval. Implement deterministic fake clients for tests. Implement only official endpoints confirmed in T01.
- **Files:** `src/integrations/x_client.py`, `src/integrations/fake_x_client.py`, `tests/test_x_client.py`
- **Depends on:** T01, T04
- **Acceptance check:** Service code depends on the interface, not raw HTTP calls; fake-client tests cover success, authentication failure, rate limit, malformed response, and timeout. Unavailable endpoint methods fail explicitly rather than silently simulating success.
- **Estimate:** 1.5 h
- **Risk:** High if API access or documentation differs from the account's actual permissions.

### T07 — Implement authorized X authentication and read-only smoke test

- **Action:** Implement the documented authentication flow for the confirmed official API. Add a connection-status check and minimal user/profile or search read smoke test. Never print tokens or secrets.
- **Files:** `src/integrations/x_auth.py`, `src/integrations/x_client.py`, `tests/integration/test_x_read_smoke.py`, `docs/x-api-feasibility.md`
- **Depends on:** T01, T04, T06
- **Acceptance check:** With user-provided credentials, a real read-only request succeeds against the authorized account; without credentials, the app gives setup instructions. Test output and logs contain no secret values.
- **Estimate:** 1.5 h
- **Risk:** High. Stop if required scopes or access are not granted.

### T08 — Build narrow prospect discovery

- **Action:** Support a small set of seed usernames and/or focused topic queries. Fetch only the fields and recent public posts allowed by the confirmed API. Add pagination bounds, rate-limit handling, and source metadata.
- **Files:** `src/services/discovery.py`, `src/schemas/prospect.py`, `tests/test_discovery.py`
- **Depends on:** T05, T06, T07
- **Acceptance check:** A real or fixture-backed discovery run produces normalized candidates with stable X user IDs and source references; pagination is bounded; repeated discovery updates existing candidates rather than creating duplicates.
- **Estimate:** 2.0 h
- **Risk:** High. Search syntax, result limits, and pricing may constrain coverage; prefer a narrow, explainable segment over broad crawling.

### T09 — Store evidence and generate qualification explanations

- **Action:** Persist profile/post evidence with URL, source type, capture time, and relevant text. Implement a transparent rule-based score for AI/robotics relevance, builder/researcher role, technical contribution, and evidence freshness. Expose score components and reasons.
- **Files:** `src/services/evidence.py`, `src/services/qualification.py`, `src/schemas/evidence.py`, `tests/test_qualification.py`
- **Depends on:** T05, T08
- **Acceptance check:** Each qualified candidate has at least one inspectable evidence item; score components are reproducible; missing evidence lowers confidence rather than being inferred as fact; tests cover relevant, irrelevant, stale, and insufficient-evidence profiles.
- **Estimate:** 1.5 h
- **Risk:** Medium. A heuristic score is a prioritization aid, not an objective measure of a person's quality.

### T10 — Add evidence-grounded message drafting

- **Action:** Implement a draft-generation service that receives only stored evidence and candidate context. Prefer an approved, user-supplied model API key only if the user explicitly approves its cost and terms; otherwise use a deterministic template-based draft. Require each personalized claim to map to evidence.
- **Files:** `src/services/drafting.py`, `src/integrations/llm_client.py`, `src/schemas/draft.py`, `tests/test_drafting.py`
- **Depends on:** T03, T05, T09
- **Acceptance check:** Draft output includes evidence references for personalized claims; unsupported claims are rejected or removed; no fabricated familiarity, achievements, or relationship is generated. Both model and deterministic paths have tests.
- **Estimate:** 2.0 h
- **Risk:** High. Without an approved LLM provider, draft quality may be less natural; never hide that limitation or silently incur API costs.

### T11 — Build the discovery and candidate review UI

- **Action:** Create the operator workflow to enter seed accounts/queries, run discovery, inspect candidate evidence, and review qualification reasons. Show actual persisted counts and clear loading/error states.
- **Files:** `src/ui/`, `src/app.py`, `tests/test_ui_services.py`
- **Depends on:** T08, T09
- **Acceptance check:** Operator can run a discovery job and inspect candidate evidence without using a terminal; empty, error, and populated states work; all displayed values come from service/database results, not hard-coded demo metrics.
- **Estimate:** 2.0 h
- **Risk:** Medium. Keep UI small; do not spend time on visual polish before workflow reliability.

### T12 — Build draft review and explicit consent capture

- **Action:** Add editable draft review, evidence display, per-message operator approval, opt-out/suppression controls, and consent evidence capture for automated/batch and test sends. Keep send disabled until the operator approves each message; discovered prospects are sendable after review unless opted out.
- **Files:** `src/services/consent.py`, `src/ui/`, `tests/test_consent.py`
- **Depends on:** T02, T05, T10, T11
- **Acceptance check:** UI visibly distinguishes unapproved draft, approved draft, opted out, and the consent states used for test/automated sends. Tests prove opted-out recipients cannot proceed to send and nothing sends without per-message operator approval.
- **Estimate:** 1.5 h
- **Risk:** Critical. A bypass in this gate invalidates the compliance design.

### T13 — Implement safe, duplicate-resistant sending

- **Action:** Implement the official DM send operation only if T01 confirms access and T07 authenticates successfully. Send only on per-message operator approval; dev/test sends go only to the operator's own or consenting accounts. Persist a send-intent record before the API call; enforce unique recipient/campaign constraints; serialize competing send attempts; store returned message identifiers. Treat timeout/ambiguous outcomes as `unknown` and reconcile before retrying.
- **Files:** `src/services/outreach.py`, `src/integrations/x_client.py`, `tests/test_outreach.py`
- **Depends on:** T06, T07, T12
- **Acceptance check:** Real sending is possible only for a draft the operator approved for that message, never for opted-out recipients; dev/test sends target only own or consenting accounts. Duplicate and concurrent-send tests prove one logical send attempt. A timeout never triggers blind retry. Failed/unknown/sent states are distinguishable.
- **Estimate:** 2.0 h
- **Risk:** Critical. Do not run live send tests against non-consenting prospects. If official send access is unavailable, mark sending as blocked; do not fake a successful send.

### T14 — Add conversation/reply tracking where authorized

- **Action:** Use confirmed official DM event/conversation endpoints to retrieve replies for the authorized account. If official API permissions do not provide this, implement a clearly labelled manual status/update path and document the limitation.
- **Files:** `src/services/conversations.py`, `src/integrations/x_client.py`, `tests/test_conversations.py`
- **Depends on:** T01, T07, T13
- **Acceptance check:** Replies are linked to the correct prospect and outreach record when supported; otherwise the UI labels tracking as manual/unavailable and does not claim real-time monitoring.
- **Estimate:** 1.5 h
- **Risk:** High. DM read/event permissions may differ from send permissions.

### T15 — Add outreach history and attention-needed dashboard

- **Action:** Show actual sent, failed, unknown, replied, opted-out, and attention-needed states with timestamps and message IDs where available. Add filters by status and prospect.
- **Files:** `src/ui/`, `src/services/dashboard.py`, `tests/test_dashboard.py`
- **Depends on:** T05, T13, T14
- **Acceptance check:** Dashboard values match database queries; an ambiguous send is visibly flagged; opted-out recipients remain suppressed; no placeholder counts are shown as real activity.
- **Estimate:** 1.5 h
- **Risk:** Medium. Prefer accurate limited tracking over implied full inbox coverage.

### T16 — Run reliability, safety, and integration verification

- **Action:** Complete unit/integration tests for send-eligibility gating (per-message approval, opt-out suppression), duplicate prevention, concurrency, evidence-grounded drafts, rate limits, authentication errors, and ambiguous send outcomes. Run a controlled end-to-end test only with the operator's own accounts or consenting test participants.
- **Files:** `tests/`, `docs/test-results.md`
- **Depends on:** T08–T15
- **Acceptance check:** `uv run pytest` passes; lint/type checks selected in T03 pass; test report distinguishes mocked tests from real X API smoke tests; no real message is sent to an unconsenting recipient.
- **Estimate:** 2.0 h
- **Risk:** Critical. A green mocked test suite is not evidence that real X permissions or live sending work.

### T17 — Package setup and operational documentation

- **Action:** Document prerequisites, X Developer Console setup, required permissions, environment variables, local startup, test command, data handling, costs, known limitations, and safe test procedure. Keep first-run setup under 15 minutes after credentials are available.
- **Files:** `README.md`, `.env.example`, `docs/setup.md`, `docs/operations.md`
- **Depends on:** T16
- **Acceptance check:** A clean-environment walkthrough completes in under 15 minutes excluding external account approval/credential provisioning; no secrets are committed; all paid requirements and API usage charges are stated.
- **Estimate:** 1.5 h
- **Risk:** Medium. External X account/app approval time is outside the setup-time guarantee.

### T18 — Prepare and record the 3–5 minute demo

- **Action:** Record the actual prototype flow: start app, discover a narrow segment, inspect evidence and fit, create/edit a draft, show consent gate, send only to a consenting test account if enabled, and show resulting history/reply status. State any unavailable API capability on-screen or in narration.
- **Files:** `docs/demo-script.md`, `submission/demo.mp4`
- **Depends on:** T16, T17
- **Acceptance check:** Video is 3–5 minutes, demonstrates working paths rather than slides, uses only authorized test accounts, and clearly discloses mocked/manual/unfinished functions.
- **Estimate:** 1.5–2.0 h (recording, retakes, edit)
- **Risk:** Medium. Do not record credentials, private DMs, or personal data without permission.

### T19 — Write the one-page submission note

- **Action:** Summarize architecture, workflow, design trade-offs, compliance boundaries, verification evidence, limitations, next steps, costs, and AI coding-tool usage plus human verification.
- **Files:** `submission/one-page-writeup.md`
- **Depends on:** T16, T17
- **Acceptance check:** Fits one page; costs are itemized as actual, estimated, or zero; no unverified claim is described as complete; AI-tool use and verification are disclosed.
- **Estimate:** 1.0 h
- **Risk:** Low–Medium. Ensure the write-up matches the delivered code and demo.

### T20 — Final submission audit

- **Action:** Run the clean setup and test commands, inspect Git status and tracked files, remove secrets/test personal data, verify deliverables, and submit before the deadline.
- **Files:** `README.md`, `submission/`, `docs/test-results.md`
- **Depends on:** T17–T19
- **Acceptance check:** Source/setup, demo, and one-page write-up are present; no credentials are committed; `uv run pytest` passes; submission email is prepared for `hr@genaifund.ai` and sent before **17 November 2026, 12:00 PM GMT+7**.
- **Estimate:** 1.0 h
- **Risk:** High due to deadline. Reserve calendar time for upload and email delivery.

## 5. Decision points

| ID  | Question                                                                                                                             | Options                                                                                                                        | Default                                                                                                                    | Who decides                                              |
| --- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| D1  | Does the user's X Developer account have the official endpoints and permissions required for discovery, DM send, and reply tracking? | A. All required capabilities available; B. discovery/send available but reply read unavailable; C. required access unavailable | Verify before coding; do not assume. If C, stop and document the blocker.                                                  | User, based on Developer Console and smoke-test evidence |
| D2  | What is the X API spend ceiling?                                                                                                     | A. $0; B. user-approved small credit purchase with a hard spending cap; C. defer live integration                              | Default $0 until T01; then B — cap fixed after T01 verifies pay-per-use prices. No $1/month API plan is assumed; never spend before pricing is documented.          | User                                                     |
| D3  | Which LLM provider will generate drafts?                                                                                             | A. deterministic local templates; B. user-provided API key on an explicitly approved free tier; C. paid API                    | A. deterministic fallback; B only after checking current terms/limits and user confirmation; C requires explicit approval. | User                                                     |
| D4  | Is automated reply monitoring available under the account's actual permissions?                                                      | A. official API event/conversation access; B. manual status update; C. omit reply monitoring                                   | A if verified; otherwise B, clearly labelled.                                                                              | User, based on T01                                       |
| D5  | Is the prototype expected to be hosted?                                                                                              | A. local runnable app/source; B. hosted deployment                                                                             | A. Assignment permits source code with setup instructions; hosting introduces cost and credential exposure.                | User; hosting requires explicit approval                 |

## 6. Verification plan

Run from the repository root after each relevant task.

| Command/check                                   | Expected result                                                                      |
| ----------------------------------------------- | ------------------------------------------------------------------------------------ |
| `uv python pin 3.12`                            | `.python-version` records Python 3.12                                                |
| `uv sync`                                       | Dependencies resolve and install without undeclared global dependencies              |
| `uv run python --version`                       | Python 3.12.x                                                                        |
| `uv run python -m compileall src`               | No syntax errors                                                                     |
| `uv run pytest`                                 | All unit and integration tests pass; live API tests are explicitly marked and opt-in |
| `uv run streamlit run src/app.py`               | Local app starts and displays a usable workflow                                      |
| Manual: inspect `.env.example` and Git status   | No real secrets or credentials tracked                                               |
| Manual: run without X credentials               | App shows a clear disconnected state and setup guidance                              |
| Manual: attempt send without operator approval  | Send is blocked                                                                      |
| Manual: attempt send to opted-out recipient     | Send is blocked                                                                      |
| Automated: duplicate/concurrent send tests      | Only one logical send attempt is created                                             |
| Automated: simulated timeout after send request | State becomes `unknown`; no automatic resend                                         |
| Live smoke test with consenting test account    | Only an explicitly approved test DM is sent; returned message ID/status is persisted |
| Clean setup walkthrough                         | Completes in under 15 minutes once external credentials are provisioned              |

Use the current official references as the source of truth; re-check them during T01 because API pricing and access can change:

- X Developer Platform pricing: https://developer.x.com/
- X API documentation: https://docs.x.com/
- X Help Center — About X APIs and DM permissions: https://help.x.com/en/rules-and-policies/x-api
- X Help Center — Automation Rules (updated April 2026): https://help.x.com/en/rules-and-policies/x-automation

**Pricing note from the official Developer Platform page checked on 11 November 2026:** the surfaced pricing model is credit-based pay-per-use, not a general $1/month API subscription. The page currently lists example unit costs including Posts Read at $0.005/resource, User Read at $0.010/resource, DM Event Read at $0.010/resource, and DM Interaction Create at $0.015/request. Actual eligibility, endpoint-specific billing, free credits, and current rates must be confirmed in the user's Developer Console before spending. The separate “Not a Bot” $1 subscription information is not evidence of X API access.

**Policy note:** X's April 2026 Automation Rules prohibit unsolicited automated bulk DMs. Automated DMs require prior recipient intent/opt-in and an easy opt-out. The app enforces this regardless of operator approval: operator approval authorizes one-to-one personalized sends only, within volume caps, opt-out suppression, and rate limits.

## 7. Rollback and fallback

- **X API access unavailable:** stop live integration. Keep discovery/drafting demonstrable with clearly labelled fixtures or manually supplied candidate evidence; report that the assignment's live X workflow is blocked. Do not scrape X or automate its website.
- **Discovery available, DM send unavailable:** deliver evidence-backed candidate discovery and drafts, but treat sending as blocked and escalate to the user immediately — a tool the fund cannot use to send fails the brief's pass gate ("If we can't use it to run outreach ourselves, it doesn't pass"). Do not simulate a successful send.
- **DM send available, reply read unavailable:** retain sent-message IDs and timestamps; expose a clearly labelled manual reply-status update. Do not claim automated inbox monitoring.
- **No approved LLM key or free tier:** use deterministic evidence-grounded draft templates. Do not incur model API charges.
- **Time pressure:** prioritize T00–T13 and a truthful minimal UI; reduce candidate volume, topic breadth, and dashboard polish. Do not remove consent checks, duplicate protection, or send-state reconciliation.
- **Unexpected external API behavior:** disable live send behind configuration, preserve local records, and use fake-client tests until the behavior is understood.
- **Accidental or questionable send state:** freeze further sends for that recipient, preserve request/response logs without secrets, reconcile against official account data, and never blindly retry an ambiguous request.

## 8. Uncertainties

- [UNCERTAIN: The user's X Developer Console account, app status, endpoint access, OAuth scopes, and credit balance have not been inspected. T01 is a blocking feasibility gate.]
- [RESOLVED 11 Nov 2026: user commits ~30 h/week ≈ 23.6 h available before the 17 Nov deadline. Original task estimates total 31.0 h (not 28–30); the MUST priority tier fits at ≈ 23.0 h.]
- [UNCERTAIN: No LLM provider or API key has been selected. The plan defaults to deterministic drafting and incurs no model API cost.]
- [UNCERTAIN: Official DM event/read access may not be available under the same permissions as DM sending. Reply tracking must be verified independently.]
- [UNCERTAIN: The phrase “$1 plan” may refer to a user-facing X subscription rather than API access. Do not purchase it as an API solution without confirmation in the Developer Console.]
- [UNCERTAIN: The final repository name/path does not exist yet. Save this plan into `.opencode/plans/plan.md` after creating the repository.]

## 9. First 3 actions

1. **Confirm participation (manual, time-critical):** email `hr@genaifund.ai` before **Friday 13 November 2026, 12:00 PM (GMT+7)** — the user's action, not agent work.
2. **Create the repository** and place this file at folder docs; initialize Python 3.12 with `uv` and commit the plan before implementation.
3. **Verify X API feasibility in the Developer Console**: identify the exact official search, user lookup, DM send, and DM read/event endpoints available to the account; record required scopes, pricing, and credit requirements in `docs/x-api-feasibility.md`. Do not buy credits until T01 documents prices and the cap is fixed.
4. **Make the go/no-go decision**: proceed with the official API only if the required endpoints and permissions are available within the approved spend ceiling; otherwise document the blocker and escalate — a non-sending build does not satisfy the brief.

## Plan summary

- **Task count:** 22 (T-CONF + T00–T20); MUST tier ≈ 23.0 h vs ≈ 23.6 h available (tiers set 11 Nov 2026)
- **Decision points:** 5 (D1–D5); D2 default updated: capped spend allowed after T01 verifies pricing
- **Send eligibility updated:** per-message operator approval on every send; opt-in required only for automated/batch and dev/test sends
- **Biggest risk:** official X API access and policy-compliant DM eligibility; the assignment's live-send requirement cannot be honestly met if the required official API capability is unavailable.
