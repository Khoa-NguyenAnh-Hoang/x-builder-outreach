"""Streamlit rendering only — every action and value comes from src/ui/workflows.py
which wraps the services. No business logic here (design doc B1)."""

import json

import streamlit as st

from src.config import Settings
from src.ui import fixtures, workflows


def _discovery_client(settings: Settings):
    """Live client when credentials exist (T07+); offline fixtures otherwise —
    whichever is active is announced on screen."""
    if settings.x_bearer_token:
        from src.integrations.x_client import OfficialXClient
        st.success(
            "🟢 LIVE discovery — real X API data (app-only reads, spend capped by policy). "
            "Sending stays gated until T13."
        )
        return OfficialXClient.from_settings(settings), True
    st.warning(fixtures.OFFLINE_NOTE)
    return fixtures.offline_client(), False


def render_discover_tab(conn, settings: Settings) -> None:
    client, _live = _discovery_client(settings)

    with st.form("discover_form"):
        seeds = st.text_input("Seed usernames (comma-separated)", placeholder="fixture_robo, fixture_llmdev")
        queries = st.text_input("Topic queries (comma-separated)", placeholder="humanoid robots founders")
        max_pages = st.number_input("Max pages per query (1–3, deliberately narrow)", 1, 3, 1)
        run = st.form_submit_button("Run discovery", use_container_width=True)

    if run:
        result = workflows.run_discovery_workflow(conn, client, seeds, queries, int(max_pages))
        if isinstance(result, workflows.WorkflowError):
            st.error(result.message)
        else:
            st.success(
                f"Discovery complete — {result.run.candidates_upserted} candidate(s) processed, "
                f"{result.run.new_candidates} new."
            )
            for w in result.run.warnings:
                st.warning(w)

    st.caption("Candidates, evidence and scores are persisted in SQLite; review them in the Candidates tab.")


def render_candidates_tab(conn, settings: Settings) -> None:
    candidates = workflows.load_candidates(conn)
    if not candidates:
        st.info("No candidates yet — run discovery in the first tab.")
        return

    def _label(c):
        score = f"{c['score']:.2f}" if c["score"] is not None else "—"
        handle = f"@{c['username']}" if c["username"] else c["x_user_id"]
        return f"{score} · {handle} · {c['confidence'] or 'unqualified'}"

    selected = st.selectbox(
        "Candidate (best-qualified first)", candidates,
        format_func=_label,
        key="candidate_picker",
    )
    detail = workflows.load_candidate_detail(conn, selected["id"])
    if isinstance(detail, workflows.WorkflowError):
        st.error(detail.message)
        return

    _render_prospect_header(detail)
    _render_qualification(detail)
    _render_evidence(detail)
    _render_consent_panel(conn, detail)
    _render_draft_panel(conn, detail, settings)


def _render_prospect_header(detail) -> None:
    p = detail["prospect"]
    handle = f"@{p['username']}" if p.get("username") else p["x_user_id"]
    st.subheader(p.get("display_name") or handle)
    st.caption(
        f"{handle} · X user id {p['x_user_id']} · source: {p['source']}"
        + (f" ({p['source_query']})" if p.get("source_query") else "")
        + (f" · {p['follower_count']} followers" if p.get("follower_count") else "")
    )
    if p.get("bio"):
        st.markdown(p["bio"])


def _render_qualification(detail) -> None:
    q = detail["qualification"]
    if not q:
        st.info("Not qualified yet — run discovery to (re)score this candidate.")
        return
    st.markdown("**Why they fit** (transparent rule-based score)")
    comps = detail["components"]
    cols = st.columns(4)
    for col, (name, value) in zip(cols, comps.items()):
        col.metric(name, f"{value:.2f}")
    st.metric("total", f"{q['score']:.2f} · confidence {q['confidence']}")
    for reason in detail["reasons"]:
        st.markdown(f"- {reason}")


def _render_evidence(detail) -> None:
    st.markdown(f"**Evidence** ({len(detail['evidence'])} item(s) — every claim in a draft maps to one of these)")
    for e in detail["evidence"]:
        with st.expander(f"[{e['source_type']}] {e['url']}"):
            st.markdown(e["text"] or "*(no text captured)*")
            st.caption(f"captured {e['captured_at']}")


def _render_consent_panel(conn, detail) -> None:
    st.markdown("**Consent & suppression** (policy I2/I3/I4)")
    state: workflows.ConsentState = detail["consent_state"]
    pid = detail["prospect"]["id"]
    badges = {
        "opted_out": "🚫 OPTED OUT" if state.opted_out else "✅ not opted out",
        "consent": {"none": "consent: none", "pending": "consent: pending verification",
                    "verified": "consent: verified"}[state.consent],
        "approval": (f"approved draft #{state.approved_draft_id}" if state.approved_draft_id
                     else "no approved draft"),
    }
    st.markdown(f"`{badges['opted_out']}` · `{badges['consent']}` · `{badges['approval']}`")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Mark opted out", key=f"optout_{pid}"):
            workflows.mark_opt_out(conn, pid)
            st.rerun()
    with col2, st.form(f"consent_{pid}"):
            source = st.text_input("Consent source (who asked for a DM, where)", key=f"csrc_{pid}")
            evidence_url = st.text_input("Evidence URL (the public place they said it)", key=f"curl_{pid}")
            verify_now = st.checkbox("Verify now (operator name required)", key=f"cver_{pid}")
            verifier = st.text_input("Verified by (operator)", key=f"cverby_{pid}")
            if st.form_submit_button("Record consent (test/automated sends only)"):
                try:
                    workflows.record_consent(
                        conn, pid, source=source or "unspecified",
                        evidence_url=evidence_url or None, scope="manual",
                        verified_by=verifier if verify_now else None,
                    )
                    st.rerun()
                except Exception as err:
                    st.error(str(err))


def render_outreach_tab(conn, settings: Settings) -> None:
    data = workflows.load_dashboard(conn)
    if data.tracking_mode == "manual":
        st.info(
            "📋 Reply tracking mode: **manual** — replies are recorded by the operator "
            "below. Automated DM-event polling activates only after T07 verifies the "
            "`dm.read` entitlement (decision D4). This is not real-time monitoring."
        )

    cols = st.columns(5)
    cols[0].metric("sent", data.status_counts.get("sent", 0))
    cols[1].metric("failed", data.status_counts.get("failed", 0))
    cols[2].metric("unknown ⚠️", data.status_counts.get("unknown", 0))
    cols[3].metric("replied", data.replied_count)
    cols[4].metric("opted out", data.opted_out_count)
    st.caption(f"{data.total_attempts} outreach attempt(s) recorded in total — all values from the database")

    st.markdown("**Needs attention**")
    if not data.attention:
        st.success("Nothing needs attention — no ambiguous or failed sends.")
    for a in data.attention:
        if a.status == "unknown":
            st.error(
                f"⚠️ Attempt #{a.attempt_id} to @{a.username or a.x_user_id} is **unknown** — "
                "the API outcome was ambiguous. Reconcile against the official account before "
                "any retry (invariant I7: never blind-retry)."
            )
        else:
            st.warning(
                f"Attempt #{a.attempt_id} to @{a.username or a.x_user_id} **failed** "
                f"(mode {a.mode}, no policy denial recorded) — investigate before re-approving."
            )

    st.markdown("**Outreach history**")
    if data.recent_attempts:
        st.table({
            "id": [a.attempt_id for a in data.recent_attempts],
            "to": [f"@{a.username or a.x_user_id}" for a in data.recent_attempts],
            "status": [a.status for a in data.recent_attempts],
            "mode": [a.mode for a in data.recent_attempts],
            "msg id": [a.x_event_id or "—" for a in data.recent_attempts],
            "requested": [a.requested_at for a in data.recent_attempts],
            "resolved": [a.resolved_at or "—" for a in data.recent_attempts],
            "deny reason": [a.deny_reason or "—" for a in data.recent_attempts],
        })
    else:
        st.info("No outreach attempts yet — sending arrives in T13; denials are recorded from the eligibility gate.")

    st.markdown(f"**Replies** ({len(data.replies)})")
    if st.button("Pull DM events via API (automated path)"):
        client = fixtures.offline_client()
        result = workflows.ingest_replies(conn, client)
        if isinstance(result, workflows.WorkflowError):
            st.warning(result.message)
        else:
            st.info(f"{result} new reply event(s) ingested.")
    for r in data.replies:
        icon = "✍️" if r.source == "manual" else "📩"
        with st.expander(f"{icon} [{r.source}] from @{r.username or r.prospect_id}"
                         + (f" — {r.occurred_at}" if r.occurred_at else "")):
            st.markdown(r.text or "*(no text recorded)*")
            if r.attempt_id:
                st.caption(f"linked to outreach attempt #{r.attempt_id}")

    st.markdown("**Record a reply manually** (manual tracking path)")
    candidates = workflows.load_candidates(conn)
    if not candidates:
        st.caption("No candidates yet.")
        return
    with st.form("manual_reply_form"):
        options = {c["id"]: f"@{c['username']}" if c["username"] else c["x_user_id"]
                   for c in candidates}
        pid = st.selectbox("Prospect", list(options.keys()), format_func=lambda k: options[k],
                           key="manual_reply_prospect")
        text = st.text_area("What did they reply? (paste/summarize)", key="manual_reply_text")
        if st.form_submit_button("Record reply"):
            result = workflows.record_manual_reply(conn, pid, text or None)
            if isinstance(result, workflows.WorkflowError):
                st.error(result.message)
            else:
                st.rerun()


def _render_draft_panel(conn, detail, settings: Settings) -> None:
    st.markdown("**Draft review & approval** (policy I1 — approval binds to the text as shown)")
    pid = detail["prospect"]["id"]
    drafts = detail["drafts"]

    if st.button("Generate draft from stored evidence", key=f"gen_{pid}"):
        result = workflows.draft_for_candidate(conn, pid)
        if isinstance(result, workflows.WorkflowError):
            st.error(result.message)
        else:
            st.rerun()

    latest = next((d for d in drafts if d["status"] in ("draft", "approved")), None)
    if latest is None:
        st.info("No draft yet — generate one above.")
        return

    st.caption(f"Draft #{latest['id']} · status `{latest['status']}` · generator `{latest['generator']}`")
    edited = st.text_area("Draft text (editable — review every line before approving)",
                          value=latest["text"], key=f"draft_text_{latest['id']}", height=170)
    refs = json.loads(latest["evidence_refs"])
    if refs:
        st.caption("Grounded claims: " + " · ".join(
            f"[evidence {r['evidence_id']}] \"{r['claim']}\"" for r in refs))

    col1, col2, _ = st.columns(3)
    with col1:
        if st.button("Save edit", key=f"save_{latest['id']}") and edited != latest["text"]:
            workflows.save_draft_edit(conn, latest["id"], edited)
            st.rerun()
    with col2:
        if latest["status"] == "approved":
            st.success("Approved for one send (I1)")
        elif st.button("Approve this text", key=f"appr_{latest['id']}"):
            workflows.approve_draft(conn, latest["id"])
            st.rerun()

    st.markdown("**Send eligibility gate** — the actual API send lands in T13; this gate is live now.")
    mode = st.radio("Send mode", ["operator_approved", "dev_test", "automated_batch"],
                    key=f"mode_{pid}", horizontal=True,
                    help="operator_approved: one-to-one personalised send after review; "
                         "dev_test: own/consenting accounts only; automated_batch: needs verified opt-in")
    if st.button("Evaluate eligibility", key=f"elig_{pid}"):
        decision = workflows.check_send_eligibility(conn, pid, mode, settings)
        (st.success if decision.allowed else st.error)(f"{'ALLOWED' if decision.allowed else 'DENIED'} — {decision.reason}")
        st.table({
            "check": [c.name for c in decision.checks],
            "invariant": [c.invariant for c in decision.checks],
            "result": ["✅" if c.passed else "❌" for c in decision.checks],
            "detail": [c.detail for c in decision.checks],
        })
