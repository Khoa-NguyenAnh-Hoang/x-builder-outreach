"""Operator console entry point. T04 scope: config status + setup guidance only.

Run: `uv run streamlit run src/app.py`
Discovery/review/send UI arrives in T08+; no X API calls are made from this file yet
(see docs/x-api-feasibility.md — live integration starts after the console GO).
"""

import streamlit as st

from src.config import get_settings
from src.logging_config import setup_logging

settings = get_settings()
setup_logging(secrets=settings.secret_values())

st.set_page_config(page_title="x-builder-outreach", page_icon="🎯", layout="wide")
st.title("X Builder Outreach — operator console")

missing = settings.missing_credentials()
if missing:
    st.warning("⚠️ Disconnected — X API credentials are not fully configured.")
    st.markdown(
        """
**Setup (under 5 minutes once you have console values):**

1. Copy `.env.example` to `.env`
2. Fill in the values below from the [X Developer Console](https://developer.x.com)
   (checklist: `docs/x-api-feasibility.md` §6)
3. Restart this app

Still missing after loading `.env`:
"""
    )
    st.table({"Setting": missing, "Status": ["missing" for _ in missing]})
else:
    st.success("Credentials configured. Live API checks arrive in T07; discovery UI in T08+.")

st.caption(
    f"Send caps: {settings.send_cap_15min}/15 min · {settings.send_cap_24h}/24 h "
    "(policy I5 — inside X's 15/15min and 1,440/24h per-user limits)"
)
