# GenAI Fund FDE Assignment — One-Page Write-up

**Candidate:** Hoàng Nguyễn Anh Khoa  
**Repository:** [x-builder-outreach](https://github.com/Khoa-NguyenAnh-Hoang/x-builder-outreach)  
**Setup:** See `docs/setup.md` (local setup instructions)

## What it does

A local, single-operator application for discovering AI and robotics builders on X through seed accounts and focused topic queries. It qualifies candidates using transparent, evidence-backed scoring, generates personalized DM drafts, provides an operator review and approval workflow, and tracks outreach activity and replies.

Personalized factual claims must be traceable to stored, URL-referenced evidence. Unsupported claims are rejected rather than presented as facts.

## Technical approach

Built with Python 3.12, `uv`, Streamlit, and SQLite. X API and LLM integrations are isolated behind service interfaces to keep external dependencies replaceable and testable.

The application includes:
- Bounded discovery with candidate deduplication.
- Explainable qualification scores and stored supporting evidence.
- AI-assisted drafting through Groq's free tier, with a deterministic template fallback.
- Human review and approval before sending.
- Consent and opt-out safeguards, duplicate-send prevention, and configurable sending limits.
- Persistent outreach records, failure states, and reply tracking.

Sending is restricted to permitted, explicitly authorized test scenarios. The prototype uses official X API access and does not scrape X or automate its website.

## Engineering trade-offs

- **Evidence over unrestricted generation:** AI-generated drafts are validated against stored evidence. Unsupported factual claims are rejected, with template drafting as a fallback.
- **Focused discovery over broad crawling:** bounded queries and pagination prioritize relevant candidates and predictable API usage.
- **SQLite over hosted infrastructure:** local persistence keeps deployment simple and avoids hosting costs.
- **Explicit offline mode:** fixture-based operation supports evaluation without credentials, while clearly distinguishing fixture data from live API results.
- **Reliability over automatic retries:** ambiguous send outcomes are recorded as `unknown` for reconciliation rather than blindly retried.

## Verification

The test suite contains **136 tests**, covering core application behavior and safeguards including opt-out handling, approval requirements, duplicate-send prevention, concurrency, sending limits, and unsupported-claim rejection. The default test suite uses mocked integrations; live API tests are opt-in. Ruff checks pass.

**Live verification performed:**
- OAuth 2.0 authentication and read-only API smoke tests on 13 November 2026, including search, user lookup, and `/users/me`.
- Live discovery through the application.
- One controlled DM successfully delivered to my own X account through the application's approval and sending workflow, with the returned message ID recorded.
- No messages were sent to unconsenting accounts.

## Costs

- **X API:** $5 paid credit purchase plus $5 promotional credit.
- **Reported remaining balance:** approximately $8.23, implying approximately $1.77 in credit consumption at the time of reporting.
- **LLM:** Groq free tier; no paid model usage.
- **Hosting:** none; the application runs locally.
- **Other paid tools:** none.

The application enforces its own usage limits to keep API consumption controlled.

## AI tools and verification

ChatGPT was used to develop the initial execution roadmap. ZCode CLI (GLM) assisted with implementation under my direction.

I reviewed implementation batches against acceptance criteria, inspected the resulting code, and reran tests and lint checks throughout development. I also manually reviewed compliance-gate behavior; testing caught an issue that could have incorrectly cleared an opt-out. AI-generated message content is subject to the same evidence-validation contract as template-generated content.

## Limitations and next steps

Further work could improve reply polling, qualification for Southeast Asian AI/robotics communities, rate-limit recovery, message-quality evaluation, and hosted deployment hardening.
