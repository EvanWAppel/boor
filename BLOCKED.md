# BLOCKED — what I need from Evan

Infra/credentials and product decisions — see `NEEDS-FROM-YOU.md` and `CLERK-SETUP.md`.

- [x] **Railway hosting + Postgres (SETUP-05 / DATA-05)** — live service and web deployed and smoke-tested 2026-09-26; see DEPLOY.md.
- [ ] **Real friends playtest** — Evan/Christine sign-in, campaign invitation, and a session together; steps in PLAYTEST.md. Live AI needs a confirmed dedicated capped workspace key before enabling execution.
- [ ] 🔴 **Dedicated capped Anthropic key for live AI (personal-key guardrail)** — (1) create a `boor` workspace at https://console.anthropic.com/settings/workspaces (not Default); (2) mint a key inside it; (3) set a spend limit + alert on that workspace (Limits tab; ~$10 to start); (4) in Railway → boor service → Variables, add `ANTHROPIC_API_KEY=<that key>` and `ENABLE_STANDINS=1`, then tell Claude it's in and confirm it isn't your personal/default key. Claude never needs to see the key value.
- [ ] 🔴 **Product/design decisions (yours per build-primer §11 / §6)** — resolve before the design locks: (1) in-person vs remote for v1, (2) module ingestion for published adventures (keep or kill on legal risk), (3) content sourcing (authored/imported/AI vs original-only), (4) human-DM mode architecture (primer recommends AI-DM-only), (5) group formation (bring-your-own vs matchmaking), (6) unit economics of voice-first transcription.
- [ ] 🔴 **Consequence-tier thresholds (AI-12 / §7.3)** — define concrete numbers (lost party resource, # of betrayals, etc.) that trigger graduated gating of AI character actions above the red-line binary refuse. Needed before the tier logic can be built.
- [x] **Public portfolio repository** — verified public through GitHub on 2026-09-26.
