# Test Results — T16 (dated 13 November 2026, commit at time of run)

**Command:** `uv run pytest` (default) · `uv run ruff check src tests` (lint)
**Result:** **99 passed** · ruff clean (configured ignores documented in `pyproject.toml`)
**Environment:** Windows 11, Python 3.12.10, pytest 9.2.0

---

## Mocked vs live — read this first

- **Every test in the default suite runs against deterministic test doubles** —
  `FakeXClient` (in-memory, ids prefixed `fake-`), `FakeLLMClient`, and in-memory or
  temp-file SQLite. **No network calls. No real messages. No real accounts.**
- **Live X API tests are opt-in by marker:** tests marked `@pytest.mark.live` are
  excluded from the default run (`addopts = "-m 'not live'"`). They may only run with
  `-m live` after the Developer Console GO (D1/D2) and target **only the operator's own
  or explicitly consenting accounts** (assignment ground rules).
- **As of this document: zero live tests have been run.** No real DM has been sent to
  anyone. A green mocked suite is evidence that the *logic* is correct — it is not
  evidence that live API permissions, pricing, or delivery work. That verification is
  T07 (read smoke) and T13 (controlled send), both awaiting the console GO.

## Coverage: invariant / acceptance → tests

| Requirement (design doc) | Covered by |
|---|---|
| I1 per-message approval, one send per approval | `test_consent.py::test_send_denied_without_per_message_approval`, `test_send_allowed_after_approval_in_operator_mode`, `test_consume_approval_requires_reapproval` |
| I2 opt-out suppression, absolute | `test_consent.py::test_opt_out_is_immediate_and_locks_consent_writes`, `test_send_denied...` matrix, `test_opt_out_beats_everything` |
| I3 verified opt-in for automated/batch | `test_automated_batch_requires_verified_opt_in` (none/pending/verified) |
| I4 dev/test allowlist | `test_dev_test_mode_requires_allowlist` |
| I5 volume caps (account-level) | `test_volume_caps_block_at_limit` (cross-recipient window fill) |
| I6 rate-limit respect | `test_rate_limit_keeps_partial_results_and_warns` (discovery), `RateLimitError` carries reset (T06 suite) |
| I7 duplicate prevention + concurrency | `test_db.py` duplicate-active-intent rejection, `test_competing_send_attempts_serialize_across_connections` (two connections, partial unique index); `test_duplicate_active_attempt_blocks_send` |
| Ambiguous outcomes → `unknown`, never blind-retry | `test_db.py` status CHECK + resolve paths; dashboard attention flagging (`test_dashboard.py::test_attention_flags_unknown_and_real_failures_not_policy_denials`) |
| I8 following/open-DM ≠ consent | encoded in consent capture (operator-verified records only); policy statement in design doc A1 |
| I9 secrets hygiene | `test_config.py` presence-only credential reporting; `test_logging.py` redaction filter; `.env` git-ignored (T04 check) |
| I10 evidence-grounded drafts | `test_drafting.py` — claim→evidence contract: verbatim snippet, unknown-evidence rejection, claim-not-in-text rejection, fabricated-familiarity rejection, zero-claims rejection, LLM-outage fallback |
| Discovery bounded + dedup | `test_discovery.py` — page bound, API end-signal, repeated-run upsert, rate-limit partial results, unknown seeds |
| Qualification transparency | `test_qualification.py` — reproducible scores, cited reasons, stale/irrelevant/insufficient cases, word-boundary matching |
| Reply tracking both paths | `test_conversations.py` — manual linking, API ingestion idempotency, unknown-sender skip, unavailable-endpoint raise |
| Dashboard = database | `test_dashboard.py::test_status_counts_match_database_queries` (literal SQL comparison) |
| Config validation errors actionable | `test_config.py` cap-range messages |

## Live verification checklist (pending console GO — not yet executed)

| Check | Status |
|---|---|
| OAuth 2.0 PKCE authorize + read smoke (`GET /2/users/:id`, 1-result search) | ⏳ T07 |
| Live discovery run against own account | ⏳ T07/T08 |
| Controlled send to own/consenting account (one message, operator-approved) | ⏳ T13 |
| Duplicate attempt on a *sent* prospect rejected live | ⏳ T13 |
| Reply ingestion from real `dm.read` events | ⏳ T14-automated |
| Clean-machine setup walkthrough timed < 15 min | ⏳ T20 (on a fresh checkout) |

## Not yet verified (honesty list)

- Anything touching the live X API (above table).
- Cross-platform behavior beyond this Windows dev machine.
- Demo recording (T18) and the write-up's claims audit (T19) — both upcoming.
