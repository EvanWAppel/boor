# TASKS — *boor* (AI-Assisted D&D Platform)

Task list for building the friends MVP, organized by the phases in `prd.md`.
North-star bet: **believable AI stand-ins**. Sequence deliberately protects that
bet — a playable human-DM'd table first (Phase 1), then the AI stand-in on top
(Phase 2, the make-or-break milestone).

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked/decision needed

---

## Guided gameplay

See [GUIDED-PLAY-PLAN.md](GUIDED-PLAY-PLAN.md) for the longer roadmap.

- [x] GUIDE-01 — Authored cart rescue: server-authoritative revisioned state, owned/pregen character selection, two approaches, designated-player check, success/failure consequences, host completion, replay, and duplicate-command protection. Ended sessions are read-only.
- [ ] GUIDE-02 — Playtest with Evan and Evil Evan using PLAYTEST.md; collect where the next action is unclear.
- [x] GUIDE-LOBBY — Shared character-selection lobby, explicit readiness, spectators, host start, absent/rejoin controls, and version-one compatibility.
- [x] GUIDE-TALK — Outcome-aware conversation with Mara, three shared questions without dice, a persisted party destination and ending, and v1/v2 compatibility.
- [x] GUIDE-COMBAT — Optional bounded sparring: rolled initiative, owned turns, practice HP, strike/dodge/withdraw, automatic opponent, five-round limit, host stop, replay and duplicate-turn protection. No campaign HP or inventory mutation.
- [~] GUIDE-03 — Expand into the 20–30 minute adventure. **Data-driven scene graph landed (v5, `guided_scenes.py`):** cart check → Mara conversation → a branch-specific second check (town gate: Persuasion/Insight · river landing: Perception/Stealth) → a real two-enemy fight with target selection → recap. `guided_combat` generalized to an authored enemy roster + targeting (Mara sparring path unchanged); v1–v4 runs dispatch to the legacy machine untouched and new runs start at v5. Non-lethal, encounter-scoped combat; DCs stay visible; sparring dropped from v5. Service ruff/ty/pytest green (v1–v5); web lint/build/tests green. **Custom "try something else" landed (v5):** a playing character submits a free-form proposal; the host either maps it to an authored approach (the proposer then rolls) or declines with a recorded reason — the text is always persisted in the log and never silently resolved; normal approaches are blocked while a proposal is open. **Pause/resume landed (v5):** any seated person pauses instantly (no vote); the pauser or host resumes; game actions freeze but chat stays open; optional note after pausing; scene state is held across refresh. **Still planned:** free-form adjudication beyond the host handoff, and a real two-account playtest of the full chapter (feeds GUIDE-02).

## Phase 0 — Foundations

### Repo & tooling
- [x] SETUP-01 — Next.js (App Router) web app scaffolded in `boor/web` (TS + Tailwind + ESLint, pnpm; build + lint green)
- [x] SETUP-02 — Scaffold Python AI/game service in `boor/service` (uv, pytest, ruff, ty; FastAPI `boor_service.api` exposes dice/checks/saves/combat over HTTP, 15 tests green)
- [x] SETUP-03 — CI wired (`.github/workflows/ci.yml`): **service** job runs ruff + ty + pytest via `uv` (testcontainers uses the runner's Docker; no service container needed); **web** job runs `pnpm lint` + `pnpm build`. Both green locally; triggers on push (main/`data-layer-foundations`) + PRs, with in-progress-run cancellation.
- [~] SETUP-04 — Local dev harness: run web + service together; env/secrets handling. **Web→service client landed**: Clerk-agnostic typed API client (`web/src/lib/api.ts`) + session-room WS client (`web/src/lib/ws.ts`) + `web/.env.local.example`. **One-command web+service runner still TBD.**
- [x] SETUP-05 — Railway service + web + Postgres deployed and healthchecked (2026-09-26). Fixed unsupported Docker cache mounts, URL schemes, migrations, and healthcheck settings. See DEPLOY.md / PLAYTEST.md.

### Data model & persistence
- [x] DATA-01 — Core schema: users, campaigns, memberships/invites — `boor_service.db` (SQLAlchemy 2.0 async models + repository w/ invite-accept invariants; 12 tests green on ephemeral Postgres via testcontainers)
- [x] DATA-02 — Character model: `boor_service.character.Character` — abilities, skills, saves, derived stats (AC, initiative, passive perception), roll helpers, composed HP. **Persistence landed** — `db.models.Character` (belongs to campaign, `player_id` SET NULL for NPCs/pregens) with the sheet inputs in a JSONB `sheet` blob so the still-evolving domain model reworks without a migration per field; lossless `Character.to_sheet`/`from_sheet` (pure dict transforms, re-validated on load); `repository.create_character`; migration `975c11e58f23`. *(Inventory/spells/features ride in the JSONB sheet for now, not yet first-class columns.)*
- [x] DATA-03 — Session model: `GameSession` + unified ordered `SessionEvent` timeline (typed kinds, JSON payload, prose body, AI-attribution flag); story log = narrative subset via query. `repository` helpers + 13 tests; migration `67d54ac429fa`. *(Design: unified timeline, not separate event/story tables.)*
- [x] DATA-04 — Personality-profile + standing-instructions model (per character) — `db.models.PersonalityProfile` (one-per-character: `persona`, `standing_instructions`, `risk_tolerance` enum, JSONB `traits` for the AI-01 questionnaire) + `CharacterRedLine` persisting structured red lines. Red lines reuse the guardrail `RedLineKind`/`ActionType` enums and round-trip *straight back into* `check_action` (`repository.red_lines_for`), so the DB and the pure checker can't drift; ordered by `position` (first-violation-wins is preserved). `repository.set_personality_profile` (upsert) + `add_red_line`; migration `975c11e58f23`; 9 tests green.
- [~] DATA-05 — Railway Postgres provisioned and migrations deployed. Object storage remains deferred until maps/assets are needed.
- [x] DATA-06 — Alembic wired (async, reads `DATABASE_URL`); migrations for the DATA-01/03 schema + DATA-02/04 (`975c11e58f23`), all verified reversible (enum types managed explicitly; `alembic check` clean). **Seed data landed** — `boor_service.db.seed` (`uv run python -m boor_service.db.seed`) builds a demo campaign via the real invite→accept flow with two stand-in-ready characters (persisted sheets + profiles + red lines) and a session; 4 tests, verified end-to-end against a real Postgres.
- [x] DATA-07 — **Per-character knowledge scoping** (`build-primer.md` §4.2 / the-ninth-toll
      `truths_known`). Every `SessionEvent` carries `audience` (`table` | `characters` |
      `dm`) + `visible_to` (character ids). Pure predicate in `boor_service.knowledge`
      (shared by repository, `GET /log`, the WS hub, and the stand-in so they can't
      drift). `timeline_for_character` is the stand-in's only legal view;
      `act_on_turn_for_character` loads it. Human DMs see everything as *viewers*;
      stand-ins never inherit that. Private WS frames fan out only to the DM + the
      listed characters. Migration `d07a4c1e5c0e`. Existing chat/dice default to
      `table`, so MILE-1 is unchanged. Substrate for private channels (§9).

### Auth & access (invite-only)
- [x] AUTH-01 — Accounts + login (Clerk — D-03). **Service side**: `boor_service.auth` verifies Clerk session JWTs against the public JWKS (RS256, no Clerk secret server-side) via an injectable signing-key resolver, and `repository.sync_user` mirrors the identity locally on first login (email required — Clerk session token must expose it). `get_current_user` FastAPI dep + guarded `/me`. **Web side landed & verified end-to-end**: `@clerk/nextjs` (Core 3) — `<ClerkProvider>` + `<Show when=…>` + Next 16 `web/src/proxy.ts` (`clerkMiddleware`), with `useAuth().getToken` forwarded as a Bearer header through the single `web/src/lib/auth.ts` seam (gated on the publishable key so keyless CI builds stay green). Clerk app is **invite-only**; the default session token is customized to carry `email`/`name`; `CLERK_ISSUER`/`CLERK_JWKS_URL` provisioned. **Verified live: signed-in `GET /me` → 200 with the mirrored user** (`email` + `display_name` populated).
- [~] AUTH-02 — Campaign owner invites players by link/email — invite→accept invariants live in `repository` (DATA-01); **HTTP endpoints landed**: `POST /campaigns/{id}/invites` (DM-only, returns token) + `POST /invites/{token}/accept`. **Invite UI landed (NAV-01):** DM invite form on the campaign page mints a copyable `/invite/[token]` link; `/invite/[token]` page redeems it (auto-accepts once signed in) and lands the player in the campaign. **Email delivery of the link still TBD** (DM copies + sends today).
- [x] AUTH-03 — Roles: DM vs player; per-campaign membership — `auth.dependencies.current_membership` (403 for non-members) + `require_dm` (403 for players); wired into example routes (`GET /campaigns/{id}/members` any-member, `DELETE …/members/{uid}` DM-only). Tests cover owner=DM, non-member, player-refused, DM-allowed.

### Rules engine (foundational)
- [x] RULES-01 — 5e SRD dice roller (checks, attacks, saves, damage; advantage/disadvantage) — `boor_service.dice`, 18 tests green
- [x] RULES-02 — Ability/skill check + saving-throw resolution — `boor_service.mechanics` (ability_modifier, proficiency_bonus, ability_check, skill_check w/ expertise, saving_throw)
- [x] RULES-03 — Combat math: attack rolls (nat 20/1, adv/dis), damage w/ crit doubling, HP tracking (`boor_service.combat.Combatant`: damage/heal/temp HP, unconscious state)
- [x] RULES-04 — Rules test suite (TDD): 81 tests green; crits + resistances/immunities/vulnerabilities covered
- [x] LEGAL-01 — All game content confirmed within SRD 5.1; CC-BY attribution notice in `LEGAL.md` (engine is mechanics-only, no proprietary IP)

## Phase 1 — Playable tabletop (human-DM'd)

Goal: a group runs a full live session end-to-end with a human DM. **No AI yet.**

- [~] VTT-01 — Authenticated single-process WebSocket rooms with durable/scoped timeline, presence, heartbeat, token refresh on retry, reconnect/backoff, and subscribe-before-history recovery. Concurrent timeline appends serialize in Postgres. Multi-instance broker remains deferred.
- [ ] VTT-02 — Map surface: load a map image, pan/zoom *(deferred — D-04, post-MILE-1)*
- [ ] VTT-03 — Tokens: place/move PC/NPC/monster tokens, synced live *(deferred — D-04, post-MILE-1)*
- [~] VTT-04 — Dice UI wired to rules engine; results posted to the log — `components/table/DiceRoller.tsx`: quick dice + adv/dis + custom notation → `/dice/*` → result posted to the durable log via `sendRoll`. **Verified against the local service in-browser; real friends playtest pending.**
- [x] VTT-05 — DM-only initiative validated and persisted as turn events; latest state replays on join/refresh. Tested against Postgres and in the local browser.
- [~] VTT-06 — Chat: IC + OOC channels; narration log — `Composer.tsx` (IC/OOC toggle) + `Log.tsx` (unified timeline feed, per-kind rendering, AI-attribution badge). **Local disposable-table browser verification passed; real friends playtest pending.**
- [~] VTT-07 — Presence: who's here — `Presence.tsx` off the room's presence frames. **Local disposable-table browser verification passed; real friends playtest pending.** *(Whose-turn-it-is lives in the initiative tracker.)*
- [~] VTT-08 — Character-sheet view during play (read) — `SheetPanel.tsx`: collapsible read-only party sheets (abilities/mods, HP, AC, proficiencies). **Read-only for MILE-1; edits deferred. Compile-verified only.**
- [~] VTT-09 — Responsive layout for the table — `SessionRoom.tsx` uses a `lg:` two-column grid (log + tools sidebar). **Basic; needs a real mobile pass. Compile-verified only.**
- [x] NAV-01 — **Front door / campaign+session picker.** The navigation flow that gets a signed-in user to the table: home (`/`) lists your campaigns + a create form (`CampaignDashboard`); `/campaigns/[id]` is the campaign hub (`CampaignDetail`) — DM starts/ends sessions, anyone enters a session → `/table/[sessionId]`, the roster with a DM invite form that mints a copyable `/invite/[token]` link, and a party list with a minimal create-a-PC form (`NewCharacterForm`, DATA-02 sheet inputs → `POST /campaigns/{id}/characters`); `/invite/[token]` (`AcceptInvite`) redeems an invite and drops the player in the campaign. Auth-ready gating via `useMe`/`useAuthSession` (waits for Clerk to load so no signed-out flash). Shared `components/ui.tsx` primitives (zinc theme). `pnpm lint` + `next build` green; backing API flow covered by the service suite (33 API tests green on real Postgres).
- [ ] MILE-1 — Live stack is available; local browser table smoke test passed. Real two-account Clerk/friends session still pending (Evan + Christine), see PLAYTEST.md.

## Phase 2 — AI stand-ins (THE CORE BET)

Goal: mark a player absent → AI plays their character believably, within limits.
De-risk early with a thin prototype before polishing.

- [x] AI-01 — Basic personality/voice, standing instructions, and risk-tolerance editor in the table. Full guided session-zero interviews remain ZERO-01/02.
- [x] AI-02 — Structured red-line editor for all five existing categories; persona + ordered constraints save atomically with owner/DM authorization.
- [x] AI-03 — Owner/DM can mark a character absent for a session and restore control; persistent, publicly logged transitions. Profile required before handoff.
- [x] AI-04 — Stand-in reasoning: `boor_service.ai.standin.decide_action` — persona + standing instructions + game state → Claude (`claude-opus-4-8`, adaptive thinking) structured tool call. Tools wrap the rules engine (LLM reasons, engine adjudicates); every action gated by `check_action` before dispatch. Model-mocked unit tests + env-gated live test. **`build_standin_context` now assembles the `StandInContext` straight from the persisted record** — reconstructs the domain sheet from JSONB, loads the profile (persona + risk-tolerance-as-guidance) and red lines, renders the sheet text; the live `GameState` is the only caller-supplied piece.
- [~] AI-05 — DM-triggered turn endpoint broadcasts AI events to the live table; character-scoped context, guardrails, attribution, idempotent request IDs, and control-change cancellation tested with a scripted model. Live model playtest pending; automatic encounter/HP mutation remains out of scope.
- [x] AI-06 — Respect red-lines / autonomy bounds; refuse/avoid forbidden actions — pure enforcement layer `boor_service.ai.guardrails.check_action` (Allowed | Refused), 15 tests. Wired into `decide_action`: every proposed action is gated *before* the engine rolls; refusals are logged, not executed.
- [x] AI-07 — Thinking/error feedback, one in-flight AI turn per session/process, 25-second deadline, off-thread model call, and retryable errors. Live latency tuning remains part of the playtest.
- [x] AI-08 — Attribution: every stand-in action is persisted with `ai_generated=True` on the `SessionEvent` (incl. refusals), so the timeline clearly marks AI-controlled actions.
- [ ] AI-09 — Per-player post-session recap ("here's what your character did").
      **Primer §7.5 elevates this to a first-class output, not a log:** written in the
      character's voice as decisions the character made and now lives with, delivered
      *before* the player's next session. Flagged as the product's best marketing
      surface (shareable artifact).
- [ ] AI-10 — Profile learning: refine persona from that character's session history over time
- [~] AI-11 — Thin prototype + friends playtest of stand-in believability (validate the bet). **Eval harness built** (`boor_service.evals`): scripted scenarios graded on mechanical validity, red-line adherence, and LLM-as-judge persona fidelity → scorecard (`python -m boor_service.evals`). **Live friends playtest still pending.**
- [ ] AI-12 — **Consequence tiers** (`build-primer.md` §7.3). Extend the binary
      red-line refuse (`ai/guardrails.check_action`, today: Allowed | Refused) into
      graduated gating: free below the gate; **death / permanent injury / party-resource
      loss above a threshold / betrayal of a PC / anything touching a stated boundary**
      → *deferred*, requiring Regent + table consent (GOV-*). Also §7.2: bias standing
      instructions toward **motives, not vetoes**. *(Thresholds are an open decision —
      NEEDS-FROM-YOU.md §6.)*
- [ ] MILE-2 — **Milestone:** a session runs with an absent player, AI covers, group is satisfied

## Phase 2.5 — Governance & session zero (build-primer §6, §8)

In the primer's v1 scope (§13) but absent from the current schema. Sequenced after
the stand-in works, before the AI-DM phase that makes the Regent load-bearing.

- [ ] GOV-01 — **Regent role** (§8): a human holding override authority over the AI DM.
      Rotates each arc; removable by group supermajority (replaces any rating system).
      New role beyond dm/player (`MembershipRole`).
- [ ] GOV-02 — **Three override classes** (§8): *live ruling* (unilateral, instant,
      logged, no vote) · *retcon* (binding table vote) · *safety* (unilateral, available
      to **every** player, no quorum). Each override requires a written reason +
      ethics-reflection friction; every override logged **publicly** to the group.
- [ ] GOV-03 — **No player/Regent ratings anywhere** (§8, DECIDED) — enforce as a
      standing product constraint; safety interventions never count against anyone.
- [ ] ZERO-01 — **Session zero** (§6), five phases: table charter (incl. absence policy
      + chaos-dial defaults) · solo persona interviews (async, private) · weaving
      (AI-proposed inter-character bonds) · shakedown scene (highest-value training data)
      · calibration (**not optional** — the alignment/trust loop). Feeds `PersonalityProfile`.
- [ ] ZERO-02 — **Fiction-first character interview** (§5): interview about fiction, never
      mechanics; rules engine translates fiction → legal build. Capture want/fear/line,
      speech register + verbal tic, per-PC relationships, and **player-level boundaries**
      (→ stand-in guardrails / AI-02). Single shared interface; reframed for experienced
      players as "how you train your stand-in."

## Phase 3 — AI DM & swappable DM

- [ ] DM-01 — AI DM: narrate scenes, voice NPCs, adjudicate 5e rules
- [ ] DM-02 — AI DM runs encounters (controls monsters, initiative, outcomes)
- [ ] DM-03 — AI DM advances prepared plot; improvises to fill gaps
- [ ] DM-04 — Swap flow: human DM ↔ AI DM; AI covers an absent human DM from campaign notes
- [ ] DM-05 — Playtest: session run entirely by AI DM

## Phase 4 — Content pipeline

- [ ] CONTENT-01 — DM authoring tools: campaign notes, NPCs, encounters, maps
- [!] CONTENT-02 — Import SRD-compatible published modules into runnable structure.
      **⚠️ CONFLICT: `build-primer.md` §3 forbids an ingestion pipeline for published
      adventure PDFs ("single largest legal risk") and mandates original-only content.
      Blocked pending your call — see NEEDS-FROM-YOU.md §6.**
- [ ] CONTENT-03 — AI gap-fill generation (NPC / room / encounter on demand)
- [ ] CONTENT-04 — Content library / reuse across sessions

## Phase 5 — Continuity depth & polish

- [ ] CONT-01 — Long-term campaign memory the AI DM + stand-ins draw on for consistency
- [ ] CONT-02 — Relationship / faction tracking across sessions
- [ ] CONT-03 — Continuity-error detection / review (optional "flag for retcon" escape hatch)
- [ ] CONT-04 — Mobile polish + performance pass
- [ ] CONT-05 — Onboarding polish for the friends cohort

## Cross-cutting / ongoing

- [ ] X-01 — Observability + logging (per CLAUDE.md: logging to help AI debug)
- [ ] X-02 — AI cost/latency monitoring (AI Gateway usage)
- [ ] X-03 — Trust & safety: red-line enforcement audits; player feedback loop
- [~] X-04 — Success-metric instrumentation: sessions-saved, believability ratings, retention. **Stand-in believability scorecard exists** (`boor_service.evals`, optional LangSmith tracing). Session/retention metrics still TBD.

---

## Open decisions to resolve early (`[!]`)
See **`DECISIONS.md`** for full context on each.
- [x] D-02 — ✅ Railway (service) + Railway Postgres, co-located; service-owns-all-data (BFF)
- [x] D-03 — ✅ Clerk (direct at clerk.com); service verifies Clerk JWTs via JWKS
- [x] D-01 — ✅ Self-hosted WebSockets on the FastAPI service
- [x] D-04 — ✅ **Theater-of-the-mind** for MILE-1: chat (IC + OOC) + dice→log +
      initiative/turn tracker + read-only sheet view + presence. **No map/tokens**
      (VTT-02/03 deferred) — a map isn't needed to validate the north-star AI
      stand-in bet, and it's the heaviest surface. Resist re-adding it pre-MILE-1.

**Locked architecture (2026-08-14):** single Railway project — Next.js (Node) +
FastAPI service + Railway Postgres, co-located; Vercel dropped. Service owns all
data; Next.js is pure UI over HTTP/WS. Realtime = self-hosted WS. Auth = Clerk.
