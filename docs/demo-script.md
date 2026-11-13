# Demo Script — 3–5 minute end-to-end recording (T18)

**Goal:** show the prototype *working*, end to end, with honest disclosure of what is
fixture vs live and what is unfinished. Working paths only — no slides beyond the
10-second intro card.

**Before recording:** close all other windows; `data/outreach.db` fresh or seeded (your
choice — fresh shows the real first-run); **never open `.env` or any file with tokens on
screen**; do one full dry run first.

**If the live smoke test (T07) passed before recording:** use the **[LIVE]** variant of
segment 2 and say so — otherwise use the fixture variant and keep the banner visible.
Both are honest; live discovery is stronger evidence.

---

### Segment 0 — Intro (0:00–0:20) — title card
- Full-screen card: *"x-builder-outreach — X builder discovery & consent-based DM outreach. Built for GenAI Fund's FDE assignment."*
- Narration: "This is a working prototype, not a mockup — everything you'll see runs locally: Streamlit UI, services layer, SQLite. Let's start by proving the code is real."

### Segment 1 — Proof of life (0:20–0:50) — terminal
- Show: `uv sync` finishes → `uv run pytest` → **99 passed** → `uv run ruff check src tests` → clean.
- Narration: "99 tests, all passing. Every one runs on deterministic fakes — no network, no real messages. Live API tests are opt-in only and none are needed for what you're about to see."

### Segment 2 — Discovery (0:50–1:50) — app, tab 1 **[LIVE] or [FIXTURE]**
- App boots. **Keep the offline warning banner on screen** (fixture variant) — point at it: "This label is deliberate: fixture data is always announced, never passed off as live."
- Enter seeds `fixture_robo, fixture_llmdev` + one query, click **Run discovery**.
- Narration: "Seeds and narrow topic queries, hard-bounded pagination. Rate limits keep partial results instead of crashing. Candidates persist with stable X IDs — re-running updates, never duplicates." [LIVE: substitute real seeds/query, same narration minus the banner sentence.]

### Segment 3 — Why they fit (1:50–2:50) — tab 2
- Candidates ranked best-first. Open the top one: score components, "Why they fit" reasons.
- Expand **both evidence items** — show URLs.
- Narration: "A transparent rule-based score — relevance, role, contribution, freshness — with the exact matched terms cited. And every claim a draft will make is anchored to one of these evidence items, with its source URL and capture time."

### Segment 4 — Draft, approval, and the gate (2:50–4:00) — tab 2, same candidate
- Generate draft → show the grounded-claims caption → edit one word in the text area → **Save edit** → **Approve this text**.
- Eligibility panel, mode `operator_approved` → **Evaluate**: **DENIED — per-message operator approval** (before approving, if order allows) → approve → **ALLOWED**, all checks green.
- Then click **Mark opted out** → evaluate again → **DENIED — opt-out suppression**.
- Narration: "Approval binds to exactly this text, for one send. And the gate outranks the UI: an opted-out recipient can never be messaged again — no operator override exists. That's deliberate."

### Segment 5 — Tracking (4:00–4:40) — tab 3
- Metrics row; attention section; record a manual reply for the candidate → reply appears in the feed linked to the attempt.
- Narration: "Every send attempt lands here with timestamps and message IDs. Ambiguous outcomes are flagged 'unknown — reconcile before retrying'; the system never blind-retries. Reply tracking is manual until the dm.read entitlement is verified — the label says exactly that."

### Segment 6 — Disclosures (4:40–5:00) — closing card
- Card bullets: *Deterministic template drafts (LLM path behind an interface, off by default) · English-only relevance heuristics · Reply tracking manual until dm.read verified · Live sending pending Developer Console verification · Docs: setup, operations, test-results in the repo.*
- Narration: "Those limitations are stated in the docs and the write-up — a narrow, reliable tool over a broad unfinished one."

---

**Recording tips:** 1080p, zoom browser to ~125% so text is readable; speak the
disclosures, don't skip them; if a click fails, cut and retake that segment only.
**Acceptance check:** final cut is 3–5 minutes, shows working paths, uses only
labelled test data, and discloses every unfinished function.
