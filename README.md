# x-builder-outreach

GenAI Fund — X builder discovery & consent-based DM outreach prototype.

Finds AI/robotics builders on X from seed accounts or narrow segments, explains why each person fits, drafts evidence-grounded DMs for operator approval, sends approved messages safely without duplicates, and tracks what was sent and who replied.

## Setup

- Prerequisites: Python 3.12 (managed via [uv](https://docs.astral.sh/uv/)); an X developer account with API credentials is required for live discovery/sending (see `docs/plan.md`, T01).
- Install: `uv sync`
- Run app: `uv run streamlit run src/app.py` (arrives in T04)

## Status

Repository foundation (T00). Full task plan and priority tiers: [docs/plan.md](docs/plan.md).
