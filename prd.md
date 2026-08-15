# PRD — AI-Assisted D&D Platform (codename: *boor*)

**Status:** Draft v0.1
**Author:** Evan Appel
**Date:** 2026-08-11
**Audience:** Small group of friends first; broader groups later.

---

## 1. Problem

Playing Dungeons & Dragons with friends is great, but it depends on everyone
being available at the same time. In practice people drop out of individual
sessions — travel, work, life — and the group either cancels or the campaign
stalls. Not everyone is needed at every session, but a missing player's
character still leaves a hole in the party and the story.

**Core insight:** the blocker isn't the game, it's attendance. If a campaign
could continue believably when a player is absent, the group plays more, the
story stays alive, and no one dreads being the reason a session is called off.

## 2. Vision

A web-based virtual tabletop for running a persistent D&D campaign where **the
game continues even when players are missing**. When a player can't make it, an
AI steps in and plays their character — in that player's voice, within limits
they set in advance — so the party stays whole and the session happens as
planned. The DM role is equally flexible: a human can run the game, or the AI
can DM (including covering for an absent human DM).

The **north-star bet** for the first release is *believable AI stand-ins*:
absent friends should feel meaningfully present, their character should act like
them, and the group should barely miss a beat.

## 3. Goals & Non-Goals

### Goals (friends MVP)
- Run a **live, synchronous** session on a shared virtual tabletop, even when
  1+ players (or the DM) are absent.
- AI plays absent player-characters convincingly, bounded by **player-set
  standing instructions** and a personality profile.
- Support **swappable DM**: human-DM'd, AI-DM'd, or AI covering an absent human DM.
- Persist the campaign across sessions (story, party, decisions) so it feels
  continuous.
- Get a real group of friends to play a multi-session campaign and *want to keep
  using it*.

### Non-Goals (for now)
- Native mobile apps (web + mobile-friendly responsive only).
- Systems other than D&D 5e SRD.
- A full Foundry/Roll20-class VTT feature set (we build a **minimal** tabletop).
- Marketplace, monetization, or public sign-ups (comes after the friends test).
- Voice at the table (text-first; voice is a later exploration).

## 4. Target Users & Personas

- **The Regular** — plays most sessions; wants the campaign to keep momentum and
  doesn't want to carry cancellations.
- **The Sometimes-Absent Player** — can't always attend; wants their character
  handled respectfully and to not fall behind or be sidelined.
- **The DM** — invests prep; wants tools to run the game and a safety net so a
  session can still happen if *they* are the one who's out.

## 5. Key Product Decisions (locked)

| Dimension | Decision |
|---|---|
| Session format | **Live synchronous** — everyone (present + AI) plays together in real time |
| DM role | **Swappable** — human DM, AI DM, or AI covering an absent human DM |
| AI player autonomy | **Player-configurable** — absent player leaves standing instructions + personality profile that bound AI decisions |
| Interface | **Minimal custom virtual tabletop** (maps, tokens, dice, chat) — built in-house |
| Ruleset | **D&D 5e SRD 5.1** (CC-BY 4.0 licensed content) |
| Personality capture | **Both** — start from a player questionnaire/profile, refine from session history over time |
| Absent-player canon | **Canon with a recap** — AI actions are permanent; returning player gets a summary of what "they" did |
| Content source | **All three** — DM-authored campaigns, imported SRD-compatible modules, and AI generation to fill gaps |
| Platform | **Web, mobile-friendly** (responsive; works at the table on a phone/tablet) |
| Tech stack | **Next.js web app + Python AI/game service** |
| Success bet | **Believable AI stand-ins** |

## 6. Functional Requirements

### 6.1 Campaign & party
- Create a campaign; invite friends; assign each a player-character.
- Character sheets for 5e SRD (abilities, skills, HP, inventory, spells, features).
- Persistent campaign state across sessions: party roster, story log, world
  state, key decisions, relationships.

### 6.2 The live tabletop (minimal VTT)
- Shared **map** with placeable **tokens** for PCs/NPCs/monsters.
- **Dice roller** with 5e-aware rolls (checks, attacks, saves, damage; advantage/
  disadvantage).
- **Turn/initiative tracker** for combat.
- **Chat / narration log** (in-character + out-of-character channels).
- Real-time sync so all present players see the same board update live.

### 6.3 AI player stand-in (the core bet)
- Mark a player **absent** for a session; the AI takes over their character.
- AI plays within a **personality profile** + **standing instructions**:
  - Profile: goals, quirks, alignment/voice, risk tolerance, relationships.
  - Standing instructions / **red lines**: "never let my character die if
    avoidable," "don't romance NPCs," "spend gold conservatively," etc.
- AI acts in real time on the character's turn (moves the token, declares
  actions, rolls, speaks in-character in chat).
- AI competent with 5e SRD mechanics for that character (attacks, spells, skill
  checks, saves).
- Profiles **improve over time** by learning from the character's past sessions.

### 6.4 Swappable DM
- A campaign can be run by a **human DM** or the **AI DM**.
- If the human DM is absent, the **AI can DM** the session from the campaign's
  authored notes + world state.
- AI DM: narrates scenes, voices NPCs, adjudicates 5e rules, runs encounters,
  and advances the prepared plot (improvising to fill gaps).

### 6.5 Content authoring & import
- **DM-authored**: notes, NPCs, encounters, maps for a campaign.
- **Import** SRD-compatible published modules into a runnable structure.
- **AI generation** to fill gaps (an NPC, a room, an encounter) on demand and
  when improvising as DM.

### 6.6 Continuity & recap
- After each session, generate a **recap**; for absent players, a personalized
  "here's what your character did" summary.
- AI actions taken for an absent player are **canon** by default.
- Running **story log / memory** the AI DM and stand-ins draw on for consistency.

### 6.7 Access (friends release)
- Invite-only accounts; a campaign owner invites players by link/email.
- Lightweight presence: who's here, who's absent, who's AI-controlled this session.

## 7. Non-Functional Requirements

- **Believability first** — investment goes into stand-in and AI-DM quality
  before breadth of tabletop features.
- **Real-time** — low-latency shared board and chat during live sessions.
- **Transparency** — it's always clear which characters are human- vs
  AI-controlled right now; AI actions are attributable in the log.
- **Player trust/safety** — red lines are honored; AI avoids actions a player
  explicitly forbade. Recaps make AI decisions auditable.
- **Persistence/durability** — campaign state survives across sessions reliably;
  no lost progress.
- **Mobile-friendly** — usable at the table on a phone/tablet.

## 8. Proposed Architecture (initial)

- **Frontend / realtime web:** Next.js (App Router) on Vercel. Renders the
  tabletop UI, character sheets, chat; handles realtime board/chat sync.
- **AI & game-logic service:** Python service (e.g. FastAPI) responsible for:
  - 5e SRD rules engine (rolls, combat, checks).
  - AI stand-in reasoning (persona + standing instructions → in-character action).
  - AI DM (narration, NPCs, encounter running, plot advancement).
  - Personality-profile modeling and session-history learning.
  - Campaign memory / continuity store.
- **AI models:** Latest Claude models (Opus/Sonnet class) for stand-in and DM
  reasoning; routed via the AI SDK / AI Gateway.
- **Persistence:** campaign state, character sheets, session logs, personality
  profiles (Marketplace Postgres + object storage for maps/assets — TBD).
- **Realtime transport:** to be selected (e.g. websockets / a realtime service).

> *Stack is a starting decision, not final. The Python service exists so game
> logic and AI live in the Python toolchain (uv, pytest, ty) while Next.js
> handles the realtime UI and deploys cleanly on Vercel.*

## 9. Phasing / Roadmap

**Phase 0 — Foundations**
- Campaign/party/character-sheet data model; 5e SRD dice + basic rules engine;
  auth + invites; persistence.

**Phase 1 — Playable tabletop (human-DM'd)**
- Minimal VTT: map, tokens, dice, initiative, chat. A group can run a live
  session end-to-end with a human DM. No AI yet.

**Phase 2 — AI stand-ins (the core bet)**
- Personality profiles + standing instructions; mark-absent → AI plays the
  character live within limits; per-player recaps. *This is the make-or-break
  milestone for the friends release.*

**Phase 3 — AI DM & swappable DM**
- AI can DM from authored notes; covers an absent human DM.

**Phase 4 — Content pipeline**
- DM authoring tools, module import, AI gap-filling generation.

**Phase 5 — Continuity depth & polish**
- Richer long-term memory, relationship tracking, mobile polish.

## 10. Success Metrics (friends MVP)

- **Sessions saved:** # of sessions that happened *because* AI covered an absent
  player/DM instead of being cancelled.
- **Stand-in believability:** post-session ratings from present players ("did
  the absent character feel like them?") and from returning players ("was I okay
  with what 'I' did?").
- **Retention:** the group voluntarily plays a multi-session campaign to a
  natural stopping point on the platform.
- **Continuity:** low rate of continuity errors flagged by the group.

## 11. Open Questions / Risks

- **AI stand-in quality is the whole bet** — if it's not believable, the product
  doesn't clear the bar. De-risk early with a thin Phase 2 prototype.
- **Real-time AI latency** — the AI taking its turn must not stall a live table;
  need acceptable response times and graceful "AI is thinking" UX.
- **"Canon by default" + trust** — some players may resent permanent AI
  decisions. Standing red-lines and clear recaps are the mitigation; watch for
  friction and consider a lightweight "flag for retcon" escape hatch.
- **VTT scope creep** — "minimal" must stay minimal; resist rebuilding Foundry.
- **SRD boundaries** — stay within SRD 5.1 CC-BY content; no non-SRD material.
- **Content-source breadth (all three)** is large — sequence it (Phase 4) rather
  than building authoring + import + generation up front.
- **Voice** — deferred, but likely wanted later for absent-player immersion.

## 12. Out of Scope (this document)

Monetization, public onboarding, moderation-at-scale, non-5e systems, native
mobile, and marketplace/sharing of campaigns — revisit after the friends test
validates the core bet.
