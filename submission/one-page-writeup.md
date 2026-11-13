# GenAI Fund FDE Assignment — One-Page Write-up

**Candidate:** [YOUR NAME] · **Submitted:** 16 November 2026 · **Repo:** `x-builder-outreach` (source + docs; setup in `docs/setup.md`, under 15 minutes)

## What it is

A local, single-operator prototype that finds AI/robotics builders on X from seed
accounts or narrow topic queries, scores them with a transparent rule-based model whose
reasons cite matched evidence, drafts personalised DMs where **every personalised claim
is a verbatim quote from stored, URL-referenced evidence**, gets operator approval per
message, and tracks sends and replies. It refuses anything the compliance gate rejects —
by design and by test.

## Approach

Python 3.12 + uv, Streamlit UI → service layer → SQLite. All X and LLM access sits
behind frozen interfaces with one exception type per documented failure mode; services
are fully testable against deterministic fakes (99 tests, ruff-clean). The send-eligibility
gate implements the policy as code: opt-out suppression is absolute; every send requires
per-message operator approval; automated/batch sending additionally requires verified
recipient opt-in; account-level volume caps (10/15 min, 40/24 h) sit inside X's
documented limits; duplicate sends are blocked by a database constraint — a `sent`
attempt is active forever. Ambiguous API outcomes are stored as `unknown` and flagged
for reconciliation; the system never blind-retries. Only official API endpoints are
used; scraping and browser automation are explicitly out of scope.

## Trade-offs

- **Deterministic template drafts over an LLM** (default): plainer phrasing, but every
  claim is verifiably grounded; the LLM path exists behind an interface, applies the
  same claim-verification contract, and activates only with an explicitly approved
  provider. An LLM never writes a claim the evidence can't back.
- **Narrow discovery over broad crawling**: bounded pages, capped queries — reliability
  over coverage, per the brief's preference.
- **Local SQLite over a hosted service**: zero-cost, zero-credential-exposure; the
  brief's hosted-link option was declined deliberately.
- **Labelled fixtures over fake live claims**: offline mode is announced on screen;
  the test report separates mocked from live evidence (`docs/test-results.md`).

## Verification

`uv run pytest` — 99 tests covering every compliance invariant (opt-out supremacy,
per-message approval consumption, dedup under concurrency, volume caps, evidence-grounded
drafts including fabricated-familiarity rejection); `ruff` clean. The default suite is
fully mocked — no network. Live tests are opt-in via a dedicated marker. **Live status at
submission: [LIVE STATUS LINE — e.g. "OAuth + read smoke verified against the live API on
14 Nov; first controlled send to my own account; no message sent to any unconsenting
account"]**.

## Costs

X API is pay-per-use credits. Purchased **$5** of credits; the first-purchase promotion
added **$20** promotional credits (**cash exposure: $5**, credit balance ≈ $25).
Projected demo-scale usage ≈ **$15.30** (2 discovery runs, 100 lookups, 20 test sends,
reply reads — unit prices in `docs/x-api-feasibility.md`). The app cannot spend beyond
its caps and fails loudly on unentitled endpoints. No other paid tools.

## How AI tools were used, and how their output was checked

The initial execution roadmap was drafted with ChatGPT, then **verified line-by-line
against the assignment brief by an AI agent (ZCode CLI / GLM), which caught two
deliverable-breaking defects**: a compliance gate that would have made the tool unusable
for the fund's core outreach task, and a time budget that exceeded the calendar. The
implementation was written by the same agent under my direction in reviewed batches;
my verification loop was: every batch report traced acceptance criteria to named tests,
the full suite plus lint re-run locally at each step, and manual review of the gate
semantics — including a test that caught a consent-record upsert which would have
silently cleared opt-outs (fixed before commit). Docs in the repo (policy invariants,
feasibility evidence, test report) were written to make every claim checkable.

## What comes next

LLM-drafted phrasing behind the existing verification contract; automated `dm.read`
reply polling once entitlements allow; Southeast-Asia weighting in qualification;
retry/backoff on rate limits; then hand the fund the hosted-service hardening it asks for.
