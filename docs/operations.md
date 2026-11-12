# Operations — running outreach safely day to day

Audience: the GenAI Fund operator using the prototype. Compliance rules referenced
here are defined in `docs/design-and-policy.md` (invariants I1–I10) and enforced in
code — the UI renders gate outcomes but cannot override them.

## The operator workflow

1. **Discover** (tab 1): enter a few seed usernames and/or 1–3 narrow topic queries.
   Paging is hard-capped (≤3 pages); rate-limit hits keep partial results and show a
   warning. Candidates are saved with stable X user IDs — re-running updates, never
   duplicates.
2. **Review** (tab 2): candidates ranked by the transparent score (components shown).
   Open a candidate: read the **Why they fit** reasons and **every evidence item** —
   each draft claim will quote one of these, verbatim.
3. **Draft & approve**: generate a draft (deterministic template from stored evidence),
   edit it as needed, then **Approve this text**. Approval binds to the text as shown
   and is consumed by one send (I1).
4. **Eligibility gate**: pick the send mode and evaluate. Every check must pass:
   - `operator_approved` — one-to-one personalised DM to a reviewed prospect (the fund's
     normal path); still subject to caps, dedup and opt-out.
   - `dev_test` — only recipients on `TEST_RECIPIENT_ALLOWLIST` (your own or consenting
     accounts).
   - `automated_batch` — requires a **verified** recipient opt-in record; pending or
     absent consent is denied.
5. **Send** (arrives with T13): only after the gate allows. Ambiguous API outcomes are
   stored as `unknown` and flagged for manual reconciliation — **never retry blindly**.
6. **Track** (tab 3): statuses, replies, and the attention list. Record replies manually
   until automated `dm.read` polling is verified (decision D4).

## What the gate will always refuse

- Any send to an **opted-out** recipient (permanent, cannot be overridden by consent records).
- Any send **without per-message approval** — approvals are never carried over or batched.
- A **second active outreach** to a prospect (duplicate protection at the database level;
  a `sent` attempt is active forever).
- Sends **beyond the volume caps** (default 10/15 min, 40/24 h — inside X's documented limits).
- Dev/test sends to anyone **not on the allowlist**; automated sends without verified opt-in.

## Data handling

- All state lives in the local SQLite file `data/outreach.db` (gitignored). Delete it to
  reset — there is no other store, no cloud component, no telemetry.
- Credentials live only in `.env` (gitignored); secret values are redacted from logs and
  never rendered in the UI (presence-only status).
- Evidence rows keep the public source URL and capture time for every claim.

## Costs

X API is pay-per-use credits (no subscription). Documented unit prices and the
demo-scale projection (≈ $15.30, cap recommended $20, free credits may reduce net cost):
`docs/x-api-feasibility.md` §1–§3. The app never spends beyond the configured caps and
never calls endpoints that are not entitled — unavailable endpoints fail loudly.

## Known limitations (stated, not hidden)

- **Live sending/auth pending**: offline fixture mode is fully functional; live wiring
  lands with T07/T13 after the console GO.
- **Deterministic draft templates**: drafts quote real evidence verbatim — honest but
  plainer than LLM phrasing. An LLM path exists behind an interface and activates only
  with explicit provider approval (decision D3).
- **English-only relevance heuristics**: qualification term lists match English;
  non-English bios score lower (reflected in reasons, not hidden).
- **Manual reply tracking** until `dm.read` is verified (D4) — not real-time monitoring.
- **Single-user, localhost**: one operator, one SQLite file; no multi-tenant or cloud
  deployment by design.

## Safe test procedure

1. Put **only** your own/consenting X user IDs in `TEST_RECIPIENT_ALLOWLIST`.
2. Use `dev_test` mode for every early send; check the eligibility table shows all green.
3. One message at a time; verify delivery on the account; check the dashboard's
   `unknown` flag handling before any repeat.
4. Honor opt-outs immediately — the dashboard's opted-out count and the candidate badge
   must agree.
