# GenAI Fund FDE Assignment — One-Page Write-up

**Candidate:** Hoàng Nguyễn Anh Khoa · **Submitted:** 16 November 2026 · **Repo:** `x-builder-outreach` (source + docs; setup in `docs/setup.md`, under 15 minutes)

## What it is

A local, single-operator prototype that finds AI/robotics builders on X from seeds or narrow topic queries, scores them with a transparent rule-based model whose reasons cite matched evidence, drafts personalised DMs where every personalised claim is a verbatim quote of stored, URL-referenced evidence, gets operator approval per message, and tracks sends and replies. It refuses anything the compliance gate rejects — by design and by test.

## Approach

Python 3.12 + uv, Streamlit UI → service layer → SQLite. All X and LLM access sits behind frozen interfaces with one exception type per documented failure mode (136 tests, ruff-clean). The send-eligibility gate implements policy as code: opt-out suppression is absolute; every send requires per-message operator approval; automated/batch sending additionally requires verified recipient opt-in; account-level volume caps (10/15 min, 40/24 h) sit inside X's documented limits; duplicate sends are blocked at the database level — a `sent` attempt is active forever. Ambiguous outcomes are stored as `unknown` and flagged for reconciliation; the system never blind-retries. Only official API endpoints are used; scraping and browser automation are out of scope.

## Trade-offs

- **AI drafting behind a hard verification contract**: drafts come from Groq's free tier (user-approved, $0) or a deterministic template. Both satisfy the same claim-to-evidence contract — a hallucinated claim is rejected at generation and the template draft is produced instead. An LLM cannot write a claim the evidence doesn't back.
- **Narrow discovery over broad crawling**: bounded pages, capped queries — reliability over coverage, per the brief's preference.
- **Local SQLite over hosting**: zero-cost, zero-credential-exposure; the hosted-link option was declined deliberately.
- **Labelled fixtures over fake live claims**: offline mode is announced on screen; the test report separates mocked from live evidence.

## Verification

`uv run pytest` — 136 tests covering every compliance invariant (opt-out supremacy, per-message approval consumption, dedup under concurrency, volume caps, evidence-grounded drafts including fabricated-familiarity rejection); `ruff` clean. The default suite is fully mocked — no network. Live tests are opt-in via a dedicated marker. **Live status at submission: OAuth 2.0 + live read smoke verified against the real API on 13 November (search, user lookup, /users/me); live discovery runs in the UI; one controlled DM delivered to my own account through the full gate chain with its message id recorded; no message was ever sent to an unconsenting account.**

## Costs

X API is pay-per-use credits. **Cash spend: $5** (card + first purchase); X's promotion added a small percentage bonus (5% at this tier). Credit balance ≈ **$5.25**; the demo budget was sized to it (≈ $3.90). The app cannot spend beyond its caps and fails loudly on unentitled endpoints. No other paid tools.

## How AI tools were used, and how their output was checked

The initial execution roadmap was drafted with ChatGPT, then verified line-by-line against the assignment brief by an AI agent (ZCode CLI / GLM), which caught two deliverable-breaking defects: a compliance gate that would have made the tool unusable for the fund's core outreach task, and a time budget that exceeded the calendar. The implementation was written by the same agent under my direction in reviewed batches; my verification loop was: every batch report traced acceptance criteria to named tests, the full suite plus lint re-run locally at each step, and manual review of the gate semantics — including a test that caught a consent-record upsert which would have silently cleared opt-outs (fixed before commit). Live AI drafting is verified the same way: the model's output passes the same claim contract as the templates, or it is rejected.

## What comes next

Automated `dm.read` reply polling at scale; LLM phrasing iteration; Southeast-Asia weighting in qualification; retry/backoff on rate limits; then the hosted-service hardening the fund asks for.
