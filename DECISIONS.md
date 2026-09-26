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

**Update (2026-08-23):** two canonical design docs landed — **`build-primer.md`**
(product/architecture spec) and **`the-ninth-toll.md`** (the v1 campaign + an
enumerable state schema). They **confirm** the locked architecture and the
north-star bet, and add DECIDED principles now treated as canon:
- **Model never holds mechanical state** (§4.1) — already how `ai/standin.py` works.
- **Knowledge is scoped per *character*, not per campaign** (§4.2) — the primer's
  "build it first". **Landed as DATA-07:** every `SessionEvent` has `audience`
  (`table` / `characters` / `dm`) + `visible_to`; `boor_service.knowledge.is_visible`
  is the single predicate. Stand-ins call `timeline_for_character` /
  `act_on_turn_for_character` and never inherit DM omniscience. Human DMs still
  see the full record as viewers. Private WS frames fan out only to intended
  sockets. Default remains `table`, so MILE-1 theater-of-the-mind is unchanged.
- **Original in-house campaigns only; no published-module ingestion** (§3) — this
  **conflicts** with `CONTENT-02` and the "imported" content-source below; flagged
  for your call in `NEEDS-FROM-YOU.md` §6.
- Regent governance (§8), consequence tiers (§7.3), session zero (§6) — added to
  `TASKS.md` (GOV-*, AI-12, ZERO-*). Five product OPEN items (§11) →
  `NEEDS-FROM-YOU.md` §6; do not resolve unilaterally.

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

### D-04 — ✅ RESOLVED (2026-08-19): "minimal VTT" = theater-of-the-mind
The first playable table is **chat (IC + OOC) + dice→log + initiative/turn tracker
+ read-only sheet view + presence**. **No map, no tokens** (VTT-02/03 deferred
post-MILE-1). Rationale: a map is the heaviest surface and isn't needed to validate
the north-star AI stand-in bet, which reasons over game state, not pixels. Guard
against re-adding map/tokens before friends have played a theater-of-the-mind
session. Table UI is code-complete; live run blocked on Clerk + Railway.

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
- **Content sourcing** — ⚠️ **now in conflict.** This said "authored + imported +
  AI-generated," but `build-primer.md` §3 mandates **original in-house only** and
  forbids module ingestion. Resolve before Phase 4 — see `NEEDS-FROM-YOU.md` §6.
- **Voice** — deferred; revisit for absent-player immersion post-MVP.

---

## Resolved (for the record)
Locked in `prd.md`: live synchronous · swappable DM · player-configurable AI
autonomy · minimal custom VTT · D&D 5e SRD 5.1 · personality from questionnaire +
history · canon-with-recap · content from authored + imported + AI-generated ·
web + mobile-friendly · Next.js + Python AI service · north-star = believable AI
stand-ins.

---

## Portfolio presentation (2026-09-26) — *draft, confirm me*

**Decision:** promote boor from a bare work-in-progress stub to a curated
showcase on the enki portfolio *before* it has a live deployment. Chose to lead
with the **offline AI stand-in demo** as the visual (a terminal card rendered
from the real `python -m boor_service.demo` output, which runs on a scripted
reasoner with no API key, so it is reproducible) rather than wait for a live
multiplayer table. Rejected keeping it in the WIP bucket until Railway is up.

**Trade-off:** it now reads as a shipped/showcased project (and counts toward the
"working applications" tally on `/projects`) while the real-time table is written
but not deployed. Mitigated by a scrupulously candid `honestNote` on the enki
detail page stating exactly what is real vs. still-building, and by leading with
the agent slice (which *is* real and tested), not the undeployed table.

**Remaining gates (Evan-only):** (1) Railway deploy → adds a live link;
(2) flip the private repo public + apply branch protection → makes the GitHub
link work. See `BLOCKED.md`.
