# BLOCKED — what I need from Evan

Infra/credentials and product decisions — see `NEEDS-FROM-YOU.md` and `CLERK-SETUP.md`.

- [ ] 🔴 **Railway hosting + Postgres (SETUP-05 / DATA-05)** — deploy scaffolding is written and locally verified (Dockerfiles, migration release step, healthchecks, CORS; both images build + boot). Only the account-level steps remain: create a Railway project + Postgres plugin, add the `service` (root dir `/service`) and `web` (root dir `/web`), and paste the env vars. **Follow `DEPLOY.md` step-by-step** (exact values + ordering); summary in `NEEDS-FROM-YOU.md` §2.
- [ ] 🔴 **Product/design decisions (yours per build-primer §11 / §6)** — resolve before the design locks: (1) in-person vs remote for v1, (2) module ingestion for published adventures (keep or kill on legal risk), (3) content sourcing (authored/imported/AI vs original-only), (4) human-DM mode architecture (primer recommends AI-DM-only), (5) group formation (bring-your-own vs matchmaking), (6) unit economics of voice-first transcription.
- [ ] 🔴 **Consequence-tier thresholds (AI-12 / §7.3)** — define concrete numbers (lost party resource, # of betrayals, etc.) that trigger graduated gating of AI character actions above the red-line binary refuse. Needed before the tier logic can be built.
