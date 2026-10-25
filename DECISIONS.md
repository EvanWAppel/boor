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

---

## Guided adventure v5: data-driven scene graph (2026-09-27) — GUIDE-03

**Decision:** expand the guided introduction from the ~15-minute cart/Mara/sparring
slice into the fuller river-road chapter by introducing a **data-driven scene graph**
(new `guided_scenes.py`) instead of bolting another version-guarded phase onto the
`guided.py` machine. A v5 run walks a declarative graph — cart check → Mara
conversation → a branch-specific second check (town: Persuasion/Insight gate;
river: Perception/Stealth landing) → a real two-enemy fight with target selection →
recap. Chosen after confirming with Evan (both the architecture and the four content
additions: destination scene, real combat, wrap-up recap, and a second uncertain-action).

**Trade-off:** more upfront work than a v5-bolt-on (a scene registry + a generic
per-scene handler that projects into the client-facing fields), but adding future
scenes becomes authoring — a scene definition plus a transition — with no new phase
enum or version guard. The v1–v4 hand-written machine is left **byte-for-byte
untouched** and now dispatched only for runs already at those versions; new runs
start at v5. The v1–v4 test suites are pinned to the legacy version via an autouse
`guided_scenes.VERSION` monkeypatch so they keep guarding the legacy path.

**Sub-decisions (Evan-confirmed):**
- **Combat:** two enemies with an explicit target-selection step (exercises target
  legality per GUIDED-PLAY-PLAN §G4), not a single lone foe. `guided_combat` was
  generalized to an enemy roster while the Mara sparring path stayed identical.
- **Sparring dropped from v5:** the real encounter now teaches combat, so v5 omits
  the optional Mara sparring bout. Its code remains for in-flight v4 runs.
- **DCs stay visible** to players in v5 (consistent with the existing teaching style),
  rather than hidden difficulty numbers.
- **No permanent loss / no campaign mutation:** the fight is encounter-scoped HP with
  authored non-lethal consequences for defeat/withdrawal, matching the intro's safety
  scope. Pause/resume remains follow-up work.
- **Custom "try something else" (host-adjudicated, landed on v5):** in a check scene a
  playing character can submit a free-form proposal; the host maps it to an authored
  approach (the proposer then rolls) or declines with a written reason. Chosen over
  (a) silently dropping the text or (b) building model-driven free-form adjudication
  now — the plan requires the text be preserved and the handoff explicit until real
  adjudication exists. Normal approaches are blocked while a proposal is open. Added
  directly to v5 (no new version) since v5 has no shipped/persisted runs yet.
- **Pause/resume (landed on v5):** any seated participant (player or spectator) pauses
  instantly with no vote; only the **pauser or the host** resumes. Chosen over "anyone
  resumes" (one player could undo another's safety pause) and "host only" (the pauser
  would have to ask). A pause freezes **game actions only** — chat stays open so the
  table can talk about why — and the scene underneath (pending roll, open proposal,
  combat turn) is held, not discarded. The reason is an **optional note added after**
  the pause takes effect, never a precondition. v5 only; v1–v4 legacy runs untouched.
  Older v5 states without a `paused` key read as unpaused, so no migration.
- **AI guide adjudicates proposals (v5, opt-in) — confirmed by Evan 2026-10-01:**
  - *Authority:* the AI decides immediately; the host can answer first and wins. Chosen
    over "AI suggests, host confirms" (needs a human host, which solo play lacks) and a
    per-session toggle (more UI for no current need).
  - *Bounded output:* the model may only pick one of the scene's authored approaches or
    decline with a reason (JSON-schema constrained, re-validated server-side). It never
    sets outcomes, skills, or DCs; the rules engine still rolls.
  - *Fallback:* on timeout, refusal, bad output, or a pause while it thinks, the proposal
    stays open and is marked for the host. Rejected: auto-decline (would discard the
    player's idea on our failure).
  - *Execution:* a background task after the proposal is saved, so the proposer's client
    is never blocked (they can still pause instantly); the result is applied under the
    session lock only if that exact proposal is still open.
  - *Model:* `claude-opus-5` at low effort with the server-side refusal fallback
    (`fallbacks: "default"`); `ADJUDICATOR_MODEL` overrides.
  - *Labelling:* the decision is a normal guided-state event (the state reader ignores
    `ai_generated` rows) shown as "AI guide" with `ai_adjudicated: true` in its payload.
  - *Cooldown:* at most one AI call per session every 10 seconds; a proposal inside the
    window gets a 429 with the seconds remaining. The last-call time is persisted in the
    guided state (survives restarts). Chosen over relying on the spend cap alone, since
    one player could otherwise loop propose → decline as fast as the model answers.
- **Table layout: act left, read right (GUIDE-LAYOUT) — drafted 2026-10-10, awaiting Evan's confirmation:**
  - *Chosen:* on desktop, a centered, width-capped table with two independently
    scrolling columns: the scene and tools on the left, the story log and composer on
    the right. Comes from the first GUIDE-02 playtest (lines too long on a wide browser;
    too much on screen at once).
  - *Rejected:* the previous stacked layout (scene above a short log, tools sidebar), which
    made the eyes jump between three places and ran lines edge to edge; a three-column
    layout with a separate tools rail, which adds a third place to look.
  - *Scope:* desktop browsers only; phone layout is deferred. Narrow windows fall back to
    scene → log → tools in one column.
  - *Accepted trade-off (from review):* below desktop width the visual order (scene →
    log → tools) differs from the DOM/tab order (scene → tools → log), because the left
    column must be one scroll container on desktop. Desktop order matches. Revisit with
    the phone layout.
- **"Try something else" in the conversation and the fight — confirmed by Evan 2026-10-10:**
  - *Conversation:* an idea maps only to one of Mara's questions not yet asked. Rejected:
    also mapping to the destination, because one player's free text could then lock in
    the whole party's route. The destination stays an explicit button choice.
  - *Fight:* only the character whose turn it is may propose; it maps to Strike (with a
    target), Dodge, or Withdraw, or is declined and the turn stays with them. The turn
    waits (enemies don't act) while it is open. Rejected: anyone proposing at any time,
    queued for their turn (more state, less clear what happens when).
  - *AI guide:* judges these too, under the check-scene rules (host can answer first and
    wins; failures hand back to the host; same cooldown and spend cap). Rejected: host-only.
  - *Stopping the fight* with an idea still open closes it with a visible "goes
    unanswered" line in the log rather than dropping it.
- **Free-form ideas become bounded checks (check scenes) — confirmed by Evan 2026-10-10:**
  - *Outcomes:* a new check resolves against the scene's **authored** success/failure, so
    the story graph and every consequence stay authored; the AI/host adds only a one-line
    "how it could play out". Rejected: AI-written outcome text (AI prose becomes canon).
  - *Bounds:* any of the 18 SRD skills at Easy 10 / Medium 12 / Hard 15, schema-constrained
    and re-validated server-side. Rejected: scene DC only (no nuance for far-fetched ideas).
  - *Where:* check scenes only; the conversation and the fight keep mapping to offered
    options. Rejected: fight skill checks (needs new combat effects).
  - *Who:* the AI guide and the host; the host can answer first and wins. Rejected: host only.
- **AI-09 character recaps — confirmed by Evan 2026-10-10:**
  - *Trigger:* written automatically when the DM ends a session, one per character the
    AI stand-in took at least one turn for, in a background task. Rejected: a DM "write
    recaps" button (easy to forget). A failed write is kept with its reason; the DM retries.
  - *Delivery:* in-app — the campaign page ("While you were away") and a screen before the
    table on the player's next visit. Rejected for now: email (needs a provider account;
    recorded in BLOCKED.md).
  - *Visibility:* private to the character's player and the DM until the player shares it
    with the table. Rejected: whole table by default (takes the choice from the player).
  - *Response:* read-only; the player can flag lines as "not my character" with a note,
    kept for profile learning (AI-10). The recap text is never rewritten. Rejected: no
    feedback channel.
  - *Input:* only the character's scoped timeline (DATA-07) plus persona and standing
    instructions, as quoted data. Model `claude-opus-5` at medium effort, structured output,
    server-side refusal fallback; `RECAP_MODEL` overrides.
- **PLAT-DEMO-01 public demo at `boor-demo.evanappel.me` — chosen by Evan 2026-10-25 (first two bullets); the rest drafted, awaiting confirmation:**
  - *How the service knows a request is a demo request:* by its `Origin` header. The
    browser calls `service` directly from the `web` page, so the service never sees the
    demo hostname as its own `Host`; it does see it as `Origin` on every cross-origin
    fetch and WebSocket handshake. Demo mode only lowers privilege, so a spoofed
    `Origin` reaches the sandbox and nothing more. _system wires one hostname, to `web`.
    Rejected: a second service hostname (`boor-demo-api…`, two hostnames to wire) and
    proxying the API through `web` (WebSocket proxying in Next standalone is uncertain).
  - *Sandbox:* per visitor. Each browser holds a random guest id (`demo.<32 hex>`); the
    service seeds that guest's own campaign (guest hosts it, owns Thora, a session is
    open) on first sight. Rejected: one shared campaign (concurrent visitors would
    trample the same guided session).
  - *Where demo data lives:* a `boor_demo` Postgres schema on the same server (or
    `DEMO_DATABASE_URL`), reached by its own engine whose `search_path` is `boor_demo`
    only. Routing happens in `db/session.py`, so nothing in a demo request can open the
    real engine. The schema is built from ORM metadata on first demo use (no prod DB
    change until then) and rebuilt every `DEMO_RESET_HOURS` (24) and on restart.
    Rejected: a separate Railway database (more deploy work for disposable data).
  - *Limits:* `DEMO_MAX_GUESTS` (500) sandboxes between resets; new campaigns, invites
    and invite acceptance are refused on the demo; stand-in turns return 503; the AI
    guide and recaps act as off. Emails are `guest-<hex>@demo.invalid`.
