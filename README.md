# x-builder-outreach

GenAI Fund — X builder discovery & consent-based DM outreach prototype.

Finds AI/robotics builders on X from seed accounts or narrow segments, explains why each person fits (transparent, evidence-cited scoring), drafts evidence-grounded DMs for operator approval, refuses to send anything the compliance gate rejects, and tracks what was sent and who replied.

## Quick start

Run these one command at a time (works in cmd, PowerShell and bash):

```bash
uv sync
uv run pytest
uv run streamlit run src/app.py
```

Full walkthrough (< 15 minutes): **[docs/setup.md](docs/setup.md)**. Daily operator
procedures, cost notes, and known limitations: **[docs/operations.md](docs/operations.md)**.
Works offline on labelled fixture data without any credentials; live X API features
activate after Developer Console setup (`docs/x-api-feasibility.md` §6).

## Verification

- `uv run pytest` — 136 tests, all mocked, no network (live tests are opt-in via `-m live`)
- `uv run ruff check src tests` — clean
- Test report with the mocked-vs-live distinction and invariant coverage:
  **[docs/test-results.md](docs/test-results.md)**

## Design & compliance

- Architecture, invariants I1–I10, and the send-eligibility rule: **[docs/design-and-policy.md](docs/design-and-policy.md)**
- Full task plan and priority tiers: **[docs/plan.md](docs/plan.md)**

## Status

T00–T17 complete; offline prototype end-to-end (discover → qualify → draft → approval
gate → dashboard). Live X wiring (auth smoke, first send, automated reply polling)
awaits Developer Console verification — see `docs/test-results.md` for exactly what is
and is not verified live.
