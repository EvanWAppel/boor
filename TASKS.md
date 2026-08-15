# TASKS — *boor* (AI-Assisted D&D Platform)

Task list for building the friends MVP, organized by the phases in `prd.md`.
North-star bet: **believable AI stand-ins**. Sequence deliberately protects that
bet — a playable human-DM'd table first (Phase 1), then the AI stand-in on top
(Phase 2, the make-or-break milestone).

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked/decision needed

---

## Phase 0 — Foundations

### Repo & tooling
- [x] SETUP-01 — Next.js (App Router) web app scaffolded in `boor/web` (TS + Tailwind + ESLint, pnpm; build + lint green)
- [x] SETUP-02 — Scaffold Python AI/game service in `boor/service` (uv, pytest, ruff, ty; FastAPI `boor_service.api` exposes dice/checks/saves/combat over HTTP, 15 tests green)
- [ ] SETUP-03 — Wire CI (lint + typecheck + tests) for both packages
- [ ] SETUP-04 — Local dev harness: run web + service together; env/secrets handling
- [ ] SETUP-05 — Decide + provision hosting (Vercel for web; hosting for Python service)

### Data model & persistence
- [ ] DATA-01 — Core schema: users, campaigns, memberships/invites
- [~] DATA-02 — Character model: `boor_service.character.Character` — abilities, skills, saves, derived stats (AC, initiative, passive perception), roll helpers, composed HP. **Inventory/spells/features + persistence TBD** (persistence blocked on D-02)
- [ ] DATA-03 — Session model: session records, turn/event log, story log
- [ ] DATA-04 — Personality-profile + standing-instructions model (per character)
- [ ] DATA-05 — Choose + provision datastore (Postgres via Marketplace) + object storage for maps/assets
- [ ] DATA-06 — Migrations + seed data for local testing

### Auth & access (invite-only)
- [ ] AUTH-01 — Accounts + login (pick provider; invite-only)
- [ ] AUTH-02 — Campaign owner invites players by link/email
- [ ] AUTH-03 — Roles: DM vs player; per-campaign membership

### Rules engine (foundational)
- [x] RULES-01 — 5e SRD dice roller (checks, attacks, saves, damage; advantage/disadvantage) — `boor_service.dice`, 18 tests green
- [x] RULES-02 — Ability/skill check + saving-throw resolution — `boor_service.mechanics` (ability_modifier, proficiency_bonus, ability_check, skill_check w/ expertise, saving_throw)
- [x] RULES-03 — Combat math: attack rolls (nat 20/1, adv/dis), damage w/ crit doubling, HP tracking (`boor_service.combat.Combatant`: damage/heal/temp HP, unconscious state)
- [x] RULES-04 — Rules test suite (TDD): 81 tests green; crits + resistances/immunities/vulnerabilities covered
- [x] LEGAL-01 — All game content confirmed within SRD 5.1; CC-BY attribution notice in `LEGAL.md` (engine is mechanics-only, no proprietary IP)

## Phase 1 — Playable tabletop (human-DM'd)

Goal: a group runs a full live session end-to-end with a human DM. **No AI yet.**

- [ ] VTT-01 — Realtime transport (websockets / realtime service); shared session room
- [ ] VTT-02 — Map surface: load a map image, pan/zoom
- [ ] VTT-03 — Tokens: place/move PC/NPC/monster tokens, synced live to all present
- [ ] VTT-04 — Dice UI wired to rules engine; results posted to the log
- [ ] VTT-05 — Initiative / turn tracker for combat
- [ ] VTT-06 — Chat: in-character + out-of-character channels; narration log
- [ ] VTT-07 — Presence: who's here, whose turn it is
- [ ] VTT-08 — Character-sheet view during play (read + basic edits)
- [ ] VTT-09 — Mobile-friendly responsive layout for the table
- [ ] MILE-1 — **Milestone:** friends play a real human-DM'd session end-to-end

## Phase 2 — AI stand-ins (THE CORE BET)

Goal: mark a player absent → AI plays their character believably, within limits.
De-risk early with a thin prototype before polishing.

- [ ] AI-01 — Personality questionnaire UI + profile capture (goals, quirks, voice, risk tolerance, relationships)
- [ ] AI-02 — Standing instructions / red-lines model + editor ("never let me die if avoidable", etc.)
- [ ] AI-03 — Mark-player-absent flow; hand character control to AI for the session
- [ ] AI-04 — Stand-in reasoning: persona + standing instructions + game state → in-character action (Claude via AI SDK/Gateway)
- [ ] AI-05 — AI acts on its turn in real time: moves token, declares action, rolls via rules engine, speaks in chat
- [ ] AI-06 — Respect red-lines / autonomy bounds; refuse/avoid forbidden actions
- [ ] AI-07 — "AI is thinking" UX + latency budget so it never stalls the live table
- [ ] AI-08 — Attribution: log clearly marks AI-controlled actions
- [ ] AI-09 — Per-player post-session recap ("here's what your character did")
- [ ] AI-10 — Profile learning: refine persona from that character's session history over time
- [ ] AI-11 — Thin prototype + friends playtest of stand-in believability (validate the bet)
- [ ] MILE-2 — **Milestone:** a session runs with an absent player, AI covers, group is satisfied

## Phase 3 — AI DM & swappable DM

- [ ] DM-01 — AI DM: narrate scenes, voice NPCs, adjudicate 5e rules
- [ ] DM-02 — AI DM runs encounters (controls monsters, initiative, outcomes)
- [ ] DM-03 — AI DM advances prepared plot; improvises to fill gaps
- [ ] DM-04 — Swap flow: human DM ↔ AI DM; AI covers an absent human DM from campaign notes
- [ ] DM-05 — Playtest: session run entirely by AI DM

## Phase 4 — Content pipeline

- [ ] CONTENT-01 — DM authoring tools: campaign notes, NPCs, encounters, maps
- [ ] CONTENT-02 — Import SRD-compatible published modules into runnable structure
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
- [ ] X-04 — Success-metric instrumentation: sessions-saved, believability ratings, retention

---

## Open decisions to resolve early (`[!]`)
See **`DECISIONS.md`** for full context on each.
- [!] D-02 — 🔴 Datastore + hosting for the Python service (blocks all persistence)
- [!] D-03 — 🔴 Auth provider (blocks accounts/invites)
- [!] D-01 — 🔴 Realtime transport (blocks the live table)
- [!] D-04 — 🟡 How minimal is "minimal VTT" for MILE-1 (resist scope creep)
