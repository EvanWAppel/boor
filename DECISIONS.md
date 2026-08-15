# Open Decisions — *boor*

Things **you** need to resolve. These are blocking or shaping upcoming work but
aren't mine to decide. Grouped by urgency. IDs match the `[!]` items in
`TASKS.md`.

Everything built so far (the 5e rules engine + `Character` domain model) is
deliberately **infra-independent**, so none of it is blocked by these — but the
next layer (persistence, API, auth, the web app) can't start until the
🔴 blockers are resolved.

---

## 🔴 Blocking the next layer (resolve first)

### D-02 — Datastore + hosting for the Python service
**Why it matters:** everything persistent (characters, campaigns, session logs,
personality profiles) waits on this. It also decides where the Python service
runs.
- Datastore: managed Postgres (e.g. Neon via Vercel Marketplace) is the default
  lean choice; confirm or pick another.
- Where does the Python service run? (Vercel Python Functions / Fluid Compute,
  vs. a separate host like Fly/Render/Railway.) This affects latency to the
  Next.js app and how realtime is wired.
- **Needed for:** DATA-01/03/04/05/06, and the persistence half of DATA-02.

### D-03 — Auth provider
**Why it matters:** invite-only friends release needs accounts + campaign
invites before anyone can play.
- Options: Clerk (native Vercel Marketplace, fastest), Auth0, or roll-your-own.
- **Needed for:** AUTH-01/02/03.

### D-01 — Realtime transport
**Why it matters:** the live synchronous table (shared map/tokens/dice/chat)
needs low-latency multi-client sync.
- Options: raw WebSockets on the Python service, a managed realtime service
  (e.g. Ably/Pusher/Supabase Realtime), or Vercel-native primitives.
- Interacts with **D-02** (where the service runs constrains this).
- **Needed for:** VTT-01 and everything in Phase 1's live table.

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
