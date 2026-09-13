# Build Primer — TTRPG Session Platform

**Audience:** the implementation agent.
**Status:** design consolidated from a working session. Decisions are marked **DECIDED**, **RECOMMENDED**, or **OPEN**. Do not silently resolve an OPEN item — surface it.

**Companion document:** `the-ninth-toll.md` — the v1 campaign, original content, with a state schema at the end.

---

## 1. Product thesis

A platform for running fifth-edition-compatible tabletop RPG campaigns where **an AI plays a player's character when that player can't attend**.

The differentiator is not "AI dungeon master." That market is crowded. The differentiator is **continuity of play across human absence** — the campaign doesn't stall when someone misses a night.

**Core stance (DECIDED):** the stand-in's unpredictability is a *feature*, not a defect to be minimized. Players are expected to return and live with what their character did. Design toward "you'll want to hear what happened," not toward "you won't notice the difference."

**Audience (DECIDED):** beginners first. The hard part of entering this hobby is not rules complexity; it's not having a group and not knowing how to start. Every surface should assume a user who has never played.

---

## 2. Vocabulary

Use these terms consistently in code and UI.

| Term | Meaning |
|---|---|
| **Stand-in** | The AI proxy that plays an absent player's character |
| **Regent** | The human holding override authority when the DM is the AI |
| **Chaos dial** | Per-player setting controlling how boldly their stand-in acts |
| **Session zero** | The five-phase onboarding ritual (§6) |
| **Persona** | The behavioral model of a character, built from session zero + play history |
| **Recap** | In-voice narrative account delivered to a player who missed a session |
| **Registry** | (in-fiction, v1 campaign only) — see the campaign doc; do not overload this term in platform code |

---

## 3. Hard legal constraints — non-negotiable

These are not preferences. Violating them creates real exposure.

**Permitted.** SRD 5.1 and SRD 5.2.1 content, both under CC-BY-4.0. Classes, species, spells, conditions, equipment, core resolution mechanics, and the SRD monster list. Requires an attribution notice crediting Wizards of the Coast under CC-BY-4.0 in docs and about page.

**Forbidden.**
- The marks: do not name the product "Dungeons & Dragons," do not use the dragon ampersand. Nominative compatibility language ("compatible with fifth edition rules") in body copy only, never in the product name.
- Non-SRD IP: beholders, mind flayers, illithids, the artificer class, aasimar, bastion rules, and all named settings (Forgotten Realms, Barovia, Greyhawk, etc.).
- **Do not build an ingestion pipeline for published adventure PDFs.** Hosting user-uploaded module text and running derivative processing on it is the single largest legal risk in this product. No "upload your campaign book" feature.

**Content strategy (DECIDED):** original in-house campaigns only. `the-ninth-toll.md` is the v1 title.

**Caveat to surface:** the ingestion question specifically warrants review by actual counsel before any adjacent feature is built.

---

## 4. Architecture principles

**4.1 — The model never holds mechanical state. (DECIDED)**

HP, ability scores, initiative, conditions, spell slots, inventory, currency, positioning, and dice results live in a database and are mutated only by deterministic code. The LLM reads state and narrates it; it cannot write it directly. Model-proposed mechanical changes go through a validating layer that rejects illegal ones.

Rationale: an LLM tracking HP will quietly cheat, players will catch it, and trust is unrecoverable once lost.

**4.2 — Knowledge is scoped per character, never per campaign. (DECIDED)**

Every fact in the campaign record carries a visibility set. A stand-in acts on what *its character* knows, not on what the record contains. If the rogue secretly took a bribe in a private channel, an absent paladin's stand-in must not act suspicious of them.

This is load-bearing and extremely expensive to retrofit. Build it first.

**4.3 — Character creation is deterministic under the hood.**

The interview (§5) produces fiction. A rules engine translates fiction into a legal build by selecting from constrained options. The model never freehand-generates a stat block.

---

## 5. Character creation

**Single shared interface for all skill levels. (DECIDED)** Experienced players can jump straight to direct sheet editing; beginners get the interview. Same entry point.

**Interview about fiction, never mechanics.** Beginners cannot answer "Strength or Dexterity." They can answer "when trouble starts, are you in front of it or behind it?" and "name a character from anything you love who you'd want at this table." The mechanical build is an output, never a question.

**Reframe for experienced users (RECOMMENDED):** the interview is not beginner scaffolding, it is **how you train your stand-in**. That gives every player a reason to complete it, which the shared-interface decision requires.

**Capture explicitly**, because the stand-in needs these later:
- a want, a fear, a line the character won't cross
- speech register and one verbal tic
- relationship to each other PC
- **player-level boundaries** — content this player doesn't want their character involved in. Same UI. These become stand-in guardrails.

---

## 6. Session zero

Five phases. Mix synchronous and asynchronous deliberately — a five-person live group interview is unbearable.

| Phase | Mode | ~Time | Purpose |
|---|---|---|---|
| 1. Table charter | Group, live | 20 min | Cadence, tone, rules strictness, PvP, lines & veils, **absence policy** |
| 2. Solo interviews | Async, private | — | Persona capture. Private matters; people give better material unobserved |
| 3. Weaving | Group, live | 30 min | AI proposes inter-character bonds from the five drafts; players negotiate aloud |
| 4. Shakedown scene | Group, live | 30 min | Low-stakes cold open, no dice consequences. First time players *speak as* their characters |
| 5. Calibration | Solo | — | Show sample stand-in output; player corrects; regenerate. 2–3 rounds |

**Phase 1's absence policy is the one unique to this product.** Does this table want stand-ins at all? Chaos dial defaults? Can a stand-in let a character die? Agreeing this as a group *before anyone is attached* is what keeps the core feature from feeling like something done to a player.

**Phase 4 produces the most valuable training data in the system.** Phases 1–3 are players *describing* characters. Phase 4 is players *being* them. Weight accordingly.

**Phase 5 is not optional.** It is the alignment loop and the trust moment. Shipping without it makes the first real stand-in session a coin flip on retention.

---

## 7. The stand-in

**7.1 Chaos dial.** Per-player, set at session zero, adjustable. Label in-fiction, not numerically — *Cautious / In character / Bold / Feeling lucky* rather than a temperature float.

**7.2 Standing instructions are directional, not prohibitive. (RECOMMENDED)** Let players give motives ("I'm chasing my brother's killer," "my character is falling for the cleric") rather than vetoes ("don't accept the duke's offer"). Vetoes shrink the surprise the product is built on; motives aim it.

**7.3 Consequence tiers. (DECIDED in principle, thresholds OPEN)** Certain outcomes must be gated regardless of chaos dial, per the table charter:
- character death
- permanent injury or character-altering transformation
- spending or losing party resources above a threshold
- betrayal of another PC
- anything touching a player's stated boundaries

Below the gate, the stand-in acts freely. Above it, the action is deferred, or requires Regent + table consent. This is the most likely source of a rage-quit; be conservative.

**7.4 Spotlight budget.** A stand-in that talks as much as a present player starves the humans of airtime. Bias toward: decisive in combat, sparse in roleplay. This is a social constraint, not a quality one — do not "fix" it by making the stand-in more talkative.

**7.5 The recap is a first-class output, not a log.** Written in the character's voice, framed as decisions the character made and now lives with. This is the shareable artifact and quite possibly the product's best marketing surface. Deliver it before the player's next session, not at their next login.

---

## 8. Governance — AI-DM mode

**The Regent. (DECIDED)** A human holding override authority over the AI DM.

- **Rotates each arc.** Framed as an honor; functions as a burden. Prevents grievance accumulation and teaches everyone what the seat feels like.
- **Removable by group supermajority at any time**, role passes to another player. This replaces any rating system.
- **No player ratings anywhere in the product. (DECIDED)** Not for Regents, not for players. Rejected as corrosive between friends and as actively hostile to the product's own thesis — a score that penalizes unpredictability trains people to play safe.

**Three classes of override, handled differently:**

| Class | Example | Procedure |
|---|---|---|
| **Live ruling** | "Does the bridge collapse?" | Unilateral, instant, logged. No vote — voting kills session pulse |
| **Retcon** | "The AI killed my character and that was wrong" | Table vote. Binding |
| **Safety** | "We're not doing that scene" | Unilateral, available to **every** player, not just the Regent. No quorum, no discussion |

**Before any override, prompt the Regent with a short ethics reflection and require a written reason.** The friction kills most petty overrides on its own, and the reason string becomes the audit trail.

**Every override is logged publicly to the group**: what, why, how the table voted. Regent history is visible — five overrides in ten sessions reads very differently from one.

**Safety interventions never count against anyone, in any surface, ever.** If pulling that lever can cost you something, people stop pulling it.

**If the vote is advisory rather than binding, label it advisory.** A "vote" the Regent can always overrule breeds more resentment than no vote at all.

---

## 9. Private channels

Support private player-to-player and player-to-DM channels — alliances, betrayals, secret backstory. This has real table precedent (passed notes, secret rolls, hallway conversations).

Consequence: see §4.2. Private channels are the reason knowledge scoping must exist from day one.

---

## 10. Recording, consent, ownership

- **Per-person, revocable consent.** "This recording trains an AI that will speak as me" is a materially larger ask than "we're recording tonight." Provide take-level deletion.
- **In-character vs out-of-character separation is the hardest data problem in the system.** Real tables are 40% rules arguments and "hang on, someone's at the door." That noise will poison a persona. Voice channels give speaker separation but not intent separation. Prototype this early — it gates everything downstream. Options: push-to-talk IC toggle (clunky, reliable) vs. post-hoc classifier (elegant, error-prone). Test both.
- **Players own their character, their recordings, and their persona.** Portable, deletable, never used to train anything shared across tables. Make this a stated selling point, not ToS fine print — the TTRPG community is already suspicious of AI at the table and will read it.

---

## 11. OPEN — do not resolve unilaterally

1. **In-person vs. remote for v1.** Remote is dramatically easier (you own the whole channel). In-person means competing with the table itself: phones out kills the vibe, and clean per-speaker audio in a living room is a hardware problem. Recommend remote-first, but this is the founder's call.
2. **Human-DM mode.** Currently undesigned. If a human runs the game, the Regent is redundant and the app's job flips from *generating* the session to *ingesting* someone's improvisation. Different architecture. Recommend AI-DM only for v1.
3. **Unit economics.** Four-hour sessions × continuous transcription × DM agent × N persona agents. Run cost-per-session-hour against realistic hobbyist willingness-to-pay before committing to voice-first. May force a text/async-first design.
4. **Group formation.** Beginners don't have four friends on a schedule — that is the real barrier to entry. Matchmaking with strangers is a second product with its own moderation burden. "Bring your own group" targets people who already have tools. Decide deliberately.
5. **Consequence-tier thresholds** (§7.3) — needs concrete numbers.

---

## 12. Adjacent opportunity, unbuilt

If the AI can play an absent character during a session, it can play *everyone* between sessions. **Play-by-post downtime** — shopping, training, a conversation in the tavern at 2am on a Tuesday — is cheap, asynchronous, and converts a biweekly game into a continuous one. Potentially more differentiating than the absence feature itself, and it exercises exactly the same machinery. Worth prototyping once the core loop works.

---

## 13. Suggested v1 scope

Remote-only. AI-DM only. One campaign (`the-ninth-toll.md`). Text-primary with voice as an enhancement. Full session zero including calibration. Stand-ins with chaos dial, consequence tiers, and in-voice recaps. Regent with rotation, removal, and the three override classes. Per-character knowledge scoping from the first commit.

Explicit non-goals for v1: matchmaking, in-person support, human-DM mode, module ingestion, marketplace, any rating or reputation system.
