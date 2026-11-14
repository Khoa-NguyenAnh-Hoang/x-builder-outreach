# Setup — from clone to running app in under 15 minutes

The walkthrough below excludes external provisioning (X Developer Console approval,
credit purchase) — those are one-time account steps with their own wait times.

## Prerequisites

| Need | Why |
|---|---|
| [uv](https://docs.astral.sh/uv/) | manages Python 3.12 + dependencies (`uv python pin 3.12` is already committed) |
| Git | clone the repo |
| An X Developer Console app **only for live features** | offline fixture mode works without any credentials |

Install uv once: `pip install uv` (or the standalone installer from the docs site).

## Steps

```bash
git clone <repo-url>
cd x-builder-outreach
uv sync                              # creates .venv, installs exact locked deps
uv run pytest                        # 136 tests should pass (~2 s) — no network needed
copy .env.example .env               # Windows; `cp` on macOS/Linux
# fill .env (next section), then:
uv run streamlit run src/app.py      # opens http://localhost:8501
```

Without credentials the app still runs in **offline fixture mode** — discovery uses
labelled `fixture_` candidates so you can learn the workflow safely. With credentials
filled in, the UI shows "Credentials configured"; live API calls activate in T07+.

## `.env` reference

| Variable | Required for | Notes |
|---|---|---|
| `X_BEARER_TOKEN` | live discovery (search/user lookup) | App-only bearer token |
| `X_CLIENT_ID`, `X_CLIENT_SECRET` | live auth + sending (OAuth 2.0 PKCE) | from Developer Console → User authentication settings |
| `OAUTH_CALLBACK_URL` | OAuth flow | default `http://127.0.0.1:8501/callback` — must also be registered in the Console |
| `SEND_CAP_15MIN` / `SEND_CAP_24H` | sending | app caps; must stay ≤ X's 15/15min and 1440/24h |
| `TEST_RECIPIENT_ALLOWLIST` | dev/test sends | comma-separated X user IDs of your own/consenting test accounts |

Console-side checklist (permissions, callback registration, entitlements, credits):
`docs/x-api-feasibility.md` §6.

## Verify the install

- `uv run pytest` — all pass, no network access
- `uv run ruff check src tests` — clean
- `uv run streamlit run src/app.py` — title renders, three tabs; disconnected warning
  if `.env` is empty (that is correct behavior, not a bug)

## Troubleshooting

| Symptom | Fix |
|---|---|
| `SEND_CAP_15MIN must be 1..15 …` on startup | a cap in `.env` exceeds X's hard limits — fix the value |
| App shows "not fully configured" | missing keys in `.env`; the UI lists exactly which |
| DB seems stale | local data lives in `data/outreach.db` (gitignored); delete the file to reset — nothing else stores state |
| Rate-limit warnings during discovery | expected under bounded paging; results are kept, paging stops |
