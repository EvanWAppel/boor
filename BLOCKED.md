# BLOCKED — what I need from Evan

Infra/credentials and product decisions — see `NEEDS-FROM-YOU.md` and `CLERK-SETUP.md`.

- [ ] 🔴 **Railway hosting + Postgres (SETUP-05 / DATA-05)** — create a Railway project with a Postgres plugin, deploy the FastAPI service, wire `DATABASE_URL` (auto-injected), set service env vars, run `uv run alembic upgrade head` as a release step. See `NEEDS-FROM-YOU.md` §2.
- [ ] 🔴 **Product/design decisions (yours per build-primer §11 / §6)** — resolve before the design locks: (1) in-person vs remote for v1, (2) module ingestion for published adventures (keep or kill on legal risk), (3) content sourcing (authored/imported/AI vs original-only), (4) human-DM mode architecture (primer recommends AI-DM-only), (5) group formation (bring-your-own vs matchmaking), (6) unit economics of voice-first transcription.
- [ ] 🔴 **Consequence-tier thresholds (AI-12 / §7.3)** — define concrete numbers (lost party resource, # of betrayals, etc.) that trigger graduated gating of AI character actions above the red-line binary refuse. Needed before the tier logic can be built.
