# X API Feasibility — T01 (dated 11 November 2026)

**Method:** Official documentation only (docs.x.com, help.x.com). No third-party wrappers or tutorials used as evidence. Live read/auth smoke tests are deferred to T07 (need user credentials — see checklist §7). Console-specific entitlements are pending user verification (§6).

**Verdict up front: CONDITIONAL GO** for all three capabilities (discovery, sending, reply tracking). Every required endpoint is documented-available on the current pay-per-usage model at prototype-scale cost. The conditions are: (1) user confirms app permissions + credits in the Developer Console (§6), (2) spend cap is fixed (§8, recommended $20).

---

## 1. Billing model (official)

- **Pay-per-usage, credit-based; no subscriptions.** Credits are purchased upfront and "deducted in real-time as you make API requests" (docs.x.com pricing).
- **$20 in free X API credits** for saving an eligible card plus a first credit purchase; auto-recharge match "up to $50".
- Same resource requested twice within a **24-hour UTC window is billed once** (dedup) — helps repeated discovery runs.
- Cap: 3M Post reads per monthly billing cycle (far above our needs).
- The "$1 Not a Bot" subscription is a user-verification product, **not** API access.

## 2. Endpoint / access matrix

| Capability | Endpoint | Auth | Scopes (OAuth 2.0) | Documented rate limit | Documented price | Status | Evidence |
|---|---|---|---|---|---|---|---|
| (a) Post search (discovery) | `GET /2/tweets/search/recent` | App-only Bearer **or** user context | tweet.read | App 450/15min; User 300/15min; 100 posts/request; last 7 days | Posts: Read **$0.005/resource** | **DOCUMENTED-AVAILABLE** ("Available to all developers") | [Search intro](https://docs.x.com/x-api/posts/search/introduction.md), [Rate limits](https://docs.x.com/x-api/fundamentals/rate-limits), [Pricing](https://docs.x.com/x-api/getting-started/pricing.md) |
| (b) User/profile lookup | `GET /2/users/:id`, `GET /2/users/by` | App-only or user context | users.read | App 300/15min; User 900/15min | User: Read **$0.010/resource** | **DOCUMENTED-AVAILABLE** | [Rate limits](https://docs.x.com/x-api/fundamentals/rate-limits), [Pricing](https://docs.x.com/x-api/getting-started/pricing.md) |
| (c) Account authentication | OAuth 2.0 Authorization Code **with PKCE** (user context); OAuth 1.0a user context; OAuth 2.0 app-only | — | — | — | Free (auth itself unbilled) | **DOCUMENTED-AVAILABLE** | [Auth overview](https://docs.x.com/fundamentals/authentication/overview.md) |
| (d) Send DM | `POST /2/dm_conversations/with/{participant_id}/messages` | **User context only** (OAuth 2.0 PKCE or OAuth 1.0a) | `users.read`, `tweet.read`, `dm.write` | App 1,440/24h; User 15/15min **and** 1,440/24h | DM Interaction: Create **$0.015/request** | **DOCUMENTED-AVAILABLE**; returns `dm_conversation_id` + `dm_event_id` on 201 | [Send DM endpoint](https://docs.x.com/x-api/direct-messages/create-dm-message-by-participant-id), [Rate limits](https://docs.x.com/x-api/fundamentals/rate-limits), [Pricing](https://docs.x.com/x-api/getting-started/pricing.md) |
| (e) Read DM events/replies | `GET /2/dm_events`; `GET /2/dm_conversations/with/:participant_id/dm_events`; `GET /2/dm_conversations/:dm_conversation_id/dm_events` | **User context only** (3-legged OAuth) | `dm.read` (per scope registry; confirm in console) | User 15/15min (no app-only allowance); **30-day event retention** | DM Event: Read **$0.010/resource** | **DOCUMENTED-AVAILABLE** | [DM lookup intro](https://docs.x.com/x-api/direct-messages/lookup/introduction), [Rate limits](https://docs.x.com/x-api/fundamentals/rate-limits), [Pricing](https://docs.x.com/x-api/getting-started/pricing.md) |

Notes:
- Send-DM rate limits comfortably fit the product: 15 messages/15 min and 1,440/day per user → app volume caps (planned ≤40/day) sit well inside.
- Reply tracking has **30-day retention** — adequate for "who replied / needs attention" on a live prototype.
- Recent search covers the **last 7 days only** — fine for evidence freshness (plan T09); full-archive search is not needed and not budgeted.

## 3. Cost projection (prototype-scale)

| Usage item | Volume | Cost |
|---|---|---|
| Discovery: recent search, 2 runs × 10 queries × 100 posts | 2,000 posts read | $10.00 |
| User lookup: 100 profiles | 100 resources | $1.00 |
| Test sends: 20 approved DMs (own/consenting accounts) | 20 requests | $0.30 |
| Reply reads: 20 conversations × ~10 events | 200 resources | $2.00 |
| Slack for re-runs/dedup misses | — | ~$2.00 |
| **Total demo-scale spend** | | **≈ $15.30** |

→ A **$20 cap** covers the full demo with margin; the $20 free-credits offer (card + first purchase) may make the net cost $0.

## 4. Policy constraints (official automation rules — binding design input)

From [X Automation Rules](https://help.x.com/en/rules-and-policies/x-automation):

- Bulk/unsolicited automated DMs are prohibited. Automated DMs require the recipient to have "requested or clearly indicated an intent … to be contacted … via Direct Message" **before** sending, plus a clear, easy opt-out.
- Following the account / open DM settings / existing thread ≠ consent.
- OAuth authorization of the app ≠ consent to automated actions.

**Compliance mapping (already designed in plan.md):** every send is per-message operator-approved (one-to-one, personalized, no bulk queue); automated/batch sending requires recorded recipient opt-in; opt-out suppression is enforced; dev/test sends go only to the operator's own or consenting accounts. This matches the rules as documented.

## 5. GO / NO-GO

| Capability | Verdict | Condition |
|---|---|---|
| Discovery (search + lookup) | **GO** | Console shows endpoint access + credits ≥ $10; T07 smoke test succeeds |
| Sending (approved DMs) | **GO** | App permissions = Read+Write+DM; credits available; sends limited to per-message-approved, own/consenting (dev/test) recipients |
| Reply tracking | **GO** | `dm.read` scope grantable; 30-day retention acceptable (it is) |
| **Overall** | **CONDITIONAL GO** | Pending §6 console verification and §8 cap decision; **NO-GO trigger:** console shows DM endpoints not entitled to the account, or credits cannot be purchased — then escalate per plan.md rollback ("non-sending build does not satisfy the brief") |

## 6. USER-VERIFY — Developer Console checklist (cannot be verified from docs)

1. [ ] Developer account + App exist and are **approved** (DM lookup requires an approved account).
2. [ ] App permissions set to **"Read and Write" + "Direct Messages"** (App settings → User authentication settings; also set a **callback URL** for OAuth 2.0 PKCE, e.g. `http://127.0.0.1:8501/callback`).
3. [ ] **OAuth 2.0 Client ID and Client Secret** available (PKCE user-context flow).
4. [ ] Endpoint entitlements: Console shows per-endpoint access/rates for search, users, DM send, DM read (exact product names and per-endpoint rates surface only there).
5. [ ] **Credits**: current balance; ability to purchase; eligibility for the **$20 free credits** (card + first purchase).
6. [ ] Record exact product/tier names + prices shown in *your* console into this file (§2 prices are docs-level, not account-level).

## 7. Live smoke test (T07, after credentials)

Harmless read/auth checks only: OAuth 2.0 PKCE authorize → `GET /2/users/:id` on own account → one `GET /2/tweets/search/recent` with a 1-result query. **No DM send in T01/T07 smoke** — first send happens in T13 against own/consenting accounts only.

## 8. Decision (D2) — RESOLVED 13 November 2026, updated with actual promo outcome

User decision: **purchase $5 of credits** with an eligible card; cash exposure capped at
**$5**. **Actual promo outcome (13 Nov):** percentage bonus, not the flat $20 the docs
advertising mentioned — **5% bonus credits at this spend tier** (tiered toward 10% at
higher spend). Balance ≈ **$5.25–5.50**.

**Revised demo budget to fit the real balance** (dedup: same resource within 24 h bills once):

| Usage item | Volume | Cost |
|---|---|---|
| Discovery: 1 run, 5 queries × 100 posts (+ 1 re-run, deduped) | ~600 posts | ~$3.00 |
| User lookup | ~30 profiles | ~$0.30 |
| Test sends (own/consenting accounts) | 5 DMs | ~$0.08 |
| Reply reads | ~50 events | ~$0.50 |
| **Total** | | **≈ $3.90** — fits with ~$1.30 margin |

If a larger allowance is later approved, the original ≈$15 projection still applies.

## 9. Sources (official, checked 11 Nov 2026)

- Pricing: https://docs.x.com/x-api/getting-started/pricing.md
- Pay-per-usage model: https://docs.x.com/x-api/getting-started/about-x-api
- Recent search: https://docs.x.com/x-api/posts/search/introduction.md
- Rate limits: https://docs.x.com/x-api/fundamentals/rate-limits
- Auth flows: https://docs.x.com/fundamentals/authentication/overview.md
- Send DM: https://docs.x.com/x-api/direct-messages/create-dm-message-by-participant-id
- DM lookup: https://docs.x.com/x-api/direct-messages/lookup/introduction
- Automation rules: https://help.x.com/en/rules-and-policies/x-automation
- Developer policy: https://docs.x.com/developer-terms/policy
