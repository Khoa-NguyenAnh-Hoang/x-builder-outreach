"""Operator console entry point. Thin router: all logic lives in services + workflows.

Run: `uv run streamlit run src/app.py`
"""

import streamlit as st

from src.config import get_settings
from src.db import connect, init_db
from src.logging_config import setup_logging
from src.ui.pages import render_candidates_tab, render_discover_tab

settings = get_settings()
setup_logging(secrets=settings.secret_values())

DB_PATH = "data/outreach.db"
conn = connect(DB_PATH)
init_db(conn)

st.set_page_config(page_title="x-builder-outreach", page_icon="🎯", layout="wide")
st.title("X Builder Outreach — operator console")

missing = settings.missing_credentials()
if missing:
    st.warning(
        "⚠️ Disconnected — X API credentials not fully configured: "
        + ", ".join(f"`{k}`" for k in missing)
        + ". Copy `.env.example` to `.env`, fill values from the Developer Console "
        "(checklist: `docs/x-api-feasibility.md` §6), then restart. "
        "Offline fixture discovery stays usable meanwhile."
    )
else:
    st.success("Credentials configured. Live API checks arrive in T07; sending in T13.")

st.caption(
    f"Send caps: {settings.send_cap_15min}/15 min · {settings.send_cap_24h}/24 h (policy I5) · "
    f"test allowlist: {sorted(settings.test_allowlist_ids()) or 'empty'} (policy I4)"
)

tab_discover, tab_candidates = st.tabs(["1 · Discover", "2 · Candidates, drafts & consent"])
with tab_discover:
    render_discover_tab(conn, settings)
with tab_candidates:
    render_candidates_tab(conn, settings)
