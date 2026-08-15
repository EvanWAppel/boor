# Open Decisions — *boor*

Things **you** need to resolve. These are blocking or shaping upcoming work but
aren't mine to decide. Grouped by urgency. IDs match the `[!]` items in
`TASKS.md`.

Everything built so far (the 5e rules engine + `Character` domain model) is
deliberately **infra-independent**, so none of it is blocked by these — but the
next layer (persistence, API, auth, the web app) can't start until the
🔴 blockers are resolved.

**Update (2026-08-14):** the three 🔴 blockers (D-01/D-02/D-03) are **RESOLVED** —
see below. Locked architecture: a **single Railway project** hosting the Next.js
web app (Node server), the FastAPI Python service, and Railway Postgres,
co-located. **Vercel is dropped.** The Python service **owns all data** (BFF):
it's the only thing that touches Postgres; Next.js is pure UI calling the service
over HTTP/WS. Realtime is **self-hosted WebSockets on the service**. Auth is
**Clerk** (provisioned directly at clerk.com), with the service verifying Clerk
JWTs via JWKS on every HTTP/WS call.

---

## ✅ Resolved 2026-08-14 (were the 🔴 blockers)

### D-02 — Datastore + hosting for the Python service → **Railway + Railway Postgres, BFF**
- **Hosting:** Python service runs on **Railway** (always-on long-running host).
- **Datastore:** **Railway Postgres, co-located** with the service — lowest
  latency for the thing that does all the game logic, one provider, one bill.
- **Data topology:** **service-owns-all-data (BFF)** — the Python service is the
  only thing that touches Postgres and holds the domain logic; Next.js is pure
  UI + calls the service over HTTP/WS.
- The Next.js web app also runs on Railway (Node server); **Vercel is dropped**.
- **Unblocks:** DATA-01/03/04/05/06, and the persistence half of DATA-02.

### D-03 — Auth provider → **Clerk**
- **Clerk**, provisioned **directly at clerk.com** (not Vercel Marketplace,
  since Vercel is gone). Handles UI + invite-only (allowlist/invitations).
- Next.js gets the Clerk session; the **Python service verifies Clerk JWTs via
  Clerk's JWKS endpoint** on every HTTP/WS call — the service authenticates
  independently and never trusts Next.js blindly (required by the BFF split).
- **Unblocks:** AUTH-01/02/03.

### D-01 — Realtime transport → **self-hosted WebSockets on the service**
- **Self-hosted WebSockets** on the FastAPI service (viable because Railway is
  always-on). No managed realtime dependency; fits a few concurrent friend
  tables. We own reconnection/presence — keep it behind a clean interface so
  it's swappable if we ever outgrow it.
- **Unblocks:** VTT-01 and everything in Phase 1's live table.

---

## 🟡 Shaping, but not blocking yet

### D-04 — How minimal is "minimal VTT" for the first playable milestone (MILE-1)?
Define the smallest table that's fun: e.g. single map + tokens + dice + chat +
initiative, no fog-of-war/measurement/lighting. Guard against scope creep.

### Character model scope (feeds DATA-02)
The current `Character` covers ability scores, skills, saves, and derived stats.
Still undecided how deep to model:
- **Inventory / equipment** — does AC come from equipped armor, or stay a manual
  field? (Today it's a manual `base_armor_class` with unarmored fallback.)
- **Spells / spell slots** — needed before spellcaster stand-ins work well.
- **Class/race features** — how much is mechanical vs. just descriptive text.
Recommendation: keep it thin until Phase 2 (AI stand-ins) tells us what the AI
actually needs to play a character convincingly.

---

## 🟢 Later (flagged so they're not forgotten)

- **AI model wiring** — provider/route for stand-in + DM reasoning (default:
  latest Claude via AI SDK / AI Gateway). Decide before Phase 2.
- **Content sourcing** — where imported SRD-compatible modules come from, and
  the authoring format. Decide before Phase 4.
- **Voice** — deferred; revisit for absent-player immersion post-MVP.

---

## Resolved (for the record)
Locked in `prd.md`: live synchronous · swappable DM · player-configurable AI
autonomy · minimal custom VTT · D&D 5e SRD 5.1 · personality from questionnaire +
history · canon-with-recap · content from authored + imported + AI-generated ·
web + mobile-friendly · Next.js + Python AI service · north-star = believable AI
stand-ins.
