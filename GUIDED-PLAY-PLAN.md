# Guided play: from chat and tools to a first adventure

Status: first slice approved and implemented, 2026-09-26. The introduction uses
a prepared scene run by the app, with a human host. Broader OPEN product decisions
in build-primer.md remain open.

## Outcome

Two people unfamiliar with fifth-edition tabletop play can join, choose characters,
complete a short adventure, and understand their choices without consulting a
rulebook or having an experienced DM explain every step.

The app must always answer:

1. Where are we, and what is happening?
2. What are we trying to accomplish?
3. Is it my turn, and what can I do?
4. What happened because of my choice?
5. What happens next?

Guidance supplies structure, not a mandatory story outcome. Choices change what
happens. Suggested actions coexist with a way to propose a different approach.

## Story-runner direction for this slice

Who runs the story?

- **Approved first slice: prepared adventure run by the app, with a human host
  handling exceptions.** Authored scenes, choices, consequences, and encounter
  behavior are executable content. Ordinary play needs no improvisation or model
  call. The host has pause/resume and clearly explained exception handling. This
  is a proposed tutorial mode, not a decision to eliminate human or AI DM modes.
- **AI DM:** the AI chooses/narrates within the same authoritative scene and rules
  state. Requires a DM agent, scoped context, interruption/error recovery, cost
  budgets, and the primer's Regent/override governance before unattended use.
- **Assisted human DM:** the app queues scene prompts, rolls, and consequences for
  a human to approve. Fits the existing role model, but still requires someone to
  run the story; it does not fully meet the no-experienced-DM outcome.

The phases below develop shared infrastructure. The chosen runner determines who
can advance a scene, resolve a novel action, or approve a narrative consequence.
Do not call an ordinary human host a Regent unless AI-DM governance is implemented.

## First playable scope

Build a proposed 20–30 minute introductory chapter set on the river road into
Emberlow, using original material compatible with The Ninth Toll. This is a new
playable introduction, not an assertion that the existing campaign outline already
contains encounter rules, branching scripts, or balanced stat blocks.

Design it for one or two player characters initially, supporting Evan's own account
and Evil Evan. In the proposed app-run mode, the host may also play a character.
This means lobby participation and character ownership must be explicit; today's
campaign owner=DM convention is not sufficient by itself.

The introduction teaches one concept at a time:

| Beat | Player experience | What it teaches |
| --- | --- | --- |
| Arrival | Read a short scene, see the immediate goal, choose an approach | You describe intentions; the app handles rules |
| Conversation | Ask a traveler about a stranded cart; inspect or reassure | Roleplay and different ways to solve a problem |
| Uncertain action | Click “Try to free the cart,” then “Roll” when prompted | Checks, modifiers, success, and setbacks |
| Brief encounter | Choose an available action and target; see the outcome | Turn order, attacks, damage, and defensive choices |
| Resolution | Recover a keepsake, choose how to help, read the result | Choices persist and failure need not stop the story |
| Wrap-up | Review what changed and where the next session begins | Campaign continuity |

Write explicit outcomes for success, failure, withdrawal, and a party unable to
continue. Do not silently change dice results or remove choices to force success.
A required clue must have an alternate route so a failed roll cannot dead-end
progress. This introduction excludes permanent character loss and high-impact
stand-in decisions; it does not invent thresholds for the primer's OPEN policy.

Do not start by converting all 12–16 sessions of The Ninth Toll.

## What people see

### Lobby and character choice

- “Start a guided adventure” is a clear entry point alongside the current table.
- Explain the premise, approximate length, supported party size, and who is hosting.
- Let beginners choose from a few validated characters described by fiction:
  “a brave protector” or “an observant scout,” with a preview of what they can do.
- Ask for a name and one short motivation; choose only from builds supported by
  the current rules implementation. No raw ability-score form for this route.
- Keep advanced character editing available through the existing shared entry
  point, with explicit compatibility checks before joining a guided adventure.
- Each participant claims a character and marks ready. Explain missing requirements
  beside the start button, including how one person can host and play.
- Capture basic tone/content preferences and explain the pause control. This quick
  introduction is not a replacement for the primer's full session zero and stand-in
  calibration. Do not enable autonomous stand-ins through a shortcut here.

### Guided table

The primary area shows the current scene, a short goal, and the current request.
The log, character details, and general-purpose dice become supporting panels.

Example:

> **The stranded cart**
> A wheel is trapped between river stones. The traveler cannot move it alone.
> **Your goal:** get the traveler and the cart safely onto the road.
>
> **Evil Evan's character — choose an approach**
> [Look for a safe path] [Help lift the cart] [Talk to the traveler]
> [Try something else]

After “Help lift the cart”:

> **Can you shift the wheel?**
> Roll a twenty-sided die. Your character's strength training adds +4.
> [Roll]

After resolution:

> **You free the wheel.** Your roll was 13 + 4 = 17.
> The traveler pulls the cart onto the road and shows you the recovered box.
> [Continue]

The modifier and result above are illustrative. Actual values come from the
selected character and a persisted roll request, never UI copy or model guesses.
Difficulty visibility is a content policy; do not reveal hidden target values by
accident in player-facing payloads.

- Use contextual explanations (“Armor makes you harder to hit”), with optional
  details for experienced players. Teach rules when needed.
- Distinguish “Your turn,” “Waiting for Evil Evan,” “Resolving,” and “Paused.”
- Show why an action is unavailable and what the player can do instead.
- In open scenes, any eligible player can propose an action; only an active request
  or encounter imposes turn order. Do not make ordinary conversation round-based.
- For party decisions, gather choices and show their status; the runner handles a
  tie through an explicit rule. A simple group-choice UI does not imply governance
  votes for retcons or safety interventions.
- “Try something else” creates an explicit proposal for the selected runner. Until
  free-form adjudication exists, explain the human-host handoff. Never discard the
  text or falsely imply it was understood and resolved.
- Any participant can immediately pause play. A safety pause takes effect before
  collecting explanations, and never requires a group vote to activate.

## Phased development and exit criteria

### G1 — Authoritative guided session state

Build the persisted scene runtime before generating narration or adding more tools.

- Define versioned adventure content: scenes, visible text, private runner notes,
  action IDs, conditions, checks, outcomes, transitions, and encounter references.
- Pin each adventure run to its content version so later edits cannot change a
  campaign already underway.
- Persist current scene, phase, revision, participants/character claims, flags,
  pending requests, and the continuation point.
- Start/resume a run; apply transitions through typed server commands; broadcast
  committed state changes to the existing room.
- Keep live character resources separate from the sheet definition. Decide whether
  each resource belongs to the campaign or the encounter; HP must not reset merely
  because a new play session is opened.
- Define allowed actors per command and a narrow runner interface so authored,
  human, and AI runners can use the same validated transitions.

Exit: two accounts see the same scene and waiting state; a refresh, reconnect, or
service restart restores it; a stale/double command cannot advance twice; a player
cannot send a host-only transition or inspect private runner notes.

### G2 — First guided action, end to end

Build one scene and one check through the actual product UI.

- Role-aware scene panel, explicit character identity, objective, and action cards.
- Selecting an action creates a pending check for the appropriate character.
- The service chooses the skill/save, calculates the modifier from the stored sheet,
  and determines advantage/disadvantage and difficulty from validated state.
- The designated player presses “Roll.” The engine rolls once, records the result,
  applies the authored outcome, and advances the pending request atomically.
- Display the result and a short explanation, then the next available action.
- Free dice remain an optional table tool; they cannot satisfy a guided request or
  change guided game state by posting a client-supplied total.

Exit: Evan and Evil Evan complete the cart check without entering dice notation,
modifiers, target numbers, or an outcome manually. Refreshing a resolved roll
replays the same result instead of rolling again. Both success and failure continue.

**This is the first implementation milestone.** It validates the core interaction
before character interviews, broad combat coverage, or a full AI DM expand scope.

### G3 — Beginner entry and authored introductory chapter

- Ready-made legal characters, character claim, ready checks, host/player identity.
- Author the introduction's conversation/exploration scenes and bounded branches.
- Add short, dismissible first-use guidance and “What should I do?” help.
- Show party decisions, pause/resume, and a useful end-of-session summary.
- Add missing-player handling: wait, continue where legal, or transfer control only
  through the table's explicit policy. Never silently assign an AI.

Exit: a newcomer reaches their first meaningful choice without guidance from Evan;
no raw character stats are required; all authored branches have valid exits; both
accounts can pause, resume, leave, and rejoin without losing progress.

### G4 — Bounded combat the app can actually resolve

The existing dice/attack/HP helpers are useful primitives, not a complete combat
runtime. Build only enough rules coverage for the selected characters and encounter.

- Persist actors and encounter state: current/max/temp HP, applicable defenses and
  conditions, initiative, turn number, available actions, and supported resources.
- Choose a theater-of-the-mind positioning representation sufficient for supported
  actions. Movement, range, adjacency, and target legality need explicit rules; do
  not claim full combat support while those are only prose.
- Offer legal actions and targets; derive attack/damage values from validated builds.
- Resolve attacks, damage, unconsciousness, and encounter completion on the server.
- Model enemy decisions as authored behavior for this encounter under the proposed
  prepared runner. An AI runner can later propose the same typed legal actions.
- Teach defending, helping, and retreat only when their mechanical effects are
  implemented. Unsupported spells/features must not appear as usable buttons.
- Connect defeat/withdrawal to authored consequences and a continuation point.

Exit: the sample encounter reaches victory or another explicit outcome with no
manual initiative list, dice arithmetic, HP bookkeeping, or enemy-turn operation.
A player cannot act out of turn, spend a resource twice, target an invalid actor, or
reuse an expired action card.

### G5 — Stand-ins use the guided action system

- Give stand-ins the same legal actions and character-scoped facts as human players.
- Have models propose an action ID, target, and dialogue; derive mechanics from
  authoritative state. Retire model-supplied bonuses, AC, and damage for this path.
- Preserve ownership, absence consent, calibration, red lines, attribution,
  thinking/errors, latency limits, and take-back-control behavior.
- Build consequence deferral after thresholds and the appropriate authority are
  explicitly decided. Do not treat a timeout, silence, or missing player as consent.
- Produce a factual, character-scoped recap of committed decisions and consequences;
  narration must not invent actions absent from the event record.

Exit: a player taking back control cancels a pending AI proposal; the AI cannot use
hidden information or perform an action unavailable to the player; the table can
continue through model failure without losing its turn or duplicating an action.

### G6 — Validate the experience and expand deliberately

- Run the complete introduction with the two test accounts, then with actual
  newcomers who have not read this plan.
- Observe where they stop, ask what to do, or misinterpret a result; revise the
  actual interaction instead of adding a long manual.
- Expand content and rules only after the introductory loop succeeds.
- Build the broader The Ninth Toll campaign, full session zero, and the selected
  human/AI DM mode against the same persisted runtime.

## Technical boundaries

Keep Next.js as UI, FastAPI as state/rules owner, Postgres as authoritative storage,
and authenticated WebSockets for updates. Reuse existing campaigns, memberships,
characters, event visibility, timeline ordering, and reconnect infrastructure.

Suggested domain records (design names, not final migrations):

- `AdventureDefinition` / content version; immutable authored content.
- `AdventureRun`; campaign continuation, current scene, phase, revision, flags.
- `RunParticipant`; member, claimed character, readiness, host/player capabilities.
- `ActionRequest`; eligible actor, action/check parameters, status, expiry/revision.
- `CharacterResources` and `EncounterState`; deterministic live mechanical state.

A command carries an idempotency key and expected state revision. The service
verifies membership, character control, request ownership, current phase, and action
legality; it then commits state changes plus timeline events in one transaction.
Broadcast happens after commit. Reconnect restores a scoped snapshot and missed
events; client rendering and AI narration never become the source of truth.

Narrative events alone are not enough: deriving every current state by guessing
from chat will break legality checks and retries. Use explicit state, with the
existing event timeline as the record of changes. Carry private information through
the existing character visibility model; never expose hidden scene outcomes in a
client-side adventure bundle.

Before G2, fix the ended-session boundary: today's UI offers “View log,” but a
connected room must enforce read-only behavior on the server after ending. Ending
must invalidate pending requests and prevent delayed outcomes from mutating state.

## Tests and success measures

Automate state transitions, authorization, idempotency, concurrent submissions,
request ownership, ended/paused behavior, resource limits, success/failure branches,
visibility, reconnect, and late AI responses. Include a two-account end-to-end test
of lobby → scene → action → roll → outcome → resume → wrap-up.

Proposed usability targets, to validate rather than present as measured results:

- First meaningful decision within five minutes of joining, excluding sign-in delays.
- No manual dice notation, modifiers, or HP arithmetic in the guided route.
- Participants can say what they are trying to do and whose action is needed.
- Finish the introductory adventure without an experienced DM coaching the UI.
- Resume after a refresh with the same scene, resources, and pending/resolved roll.

Measure aggregate completion, stalled steps, help requests, and time-to-first-action.
Do not add player or Regent ratings; observe usability and system behavior.

## Deferred scope and unresolved decisions

Maps/tokens, broad character-building coverage, arbitrary adventure import, voice,
matchmaking, and full campaign conversion are outside this first slice. Existing
freeform tables remain available while guided mode is validated.

Needs Evan's decision: first story runner; whether the proposed short introduction
and 1–2-character party are the right test scope; and later the primer's unresolved
AI-DM governance, consequence thresholds, voice economics, group formation, and
in-person/remote scope. This plan proposes a text-first browser prototype based on
the existing app; it does not silently settle those broader product questions.

## First slice implementation

The river-road rescue is a five-minute introduction with one shared check, not
the full 20–30 minute adventure. Start it inside an active session. Each person
can select an owned character or create Rowan/Wren from a server-defined starter
sheet. A player chooses one of two approaches and becomes the designated roller.
The host can release a pending check or finish after the outcome. Both outcomes
advance the story; the failure route offers shelter rather than a retry loop.

Versioned public snapshots (`guided_cart_v1`) and command receipts are persisted
as server-authored narration events. The existing game-session row lock protects
revision checks, character creation, dice resolution, receipts, and event appends
in one transaction. No new migration is needed for this bounded slice. These
snapshots contain public content only; future hidden scenes require scoped storage.
WebSockets distribute committed events; replay and GET recover state after refresh.
An ambiguous client failure retries the same request ID without rerolling.

Ended sessions reject writes, including pending checks and delayed AI actions.
Guided tutorials disable AI stand-in actions; they make no model calls. Freeform
chat remains available for discussion. The host can release a check if its player
leaves. Custom approaches, pause/resume, encounters, inventory effects, and the
longer onboarding/adventure remain follow-up work. The brass token is narrative
state only, not an inventory item.

## Lobby follow-up

New introductions now begin in a version-two lobby. The roster initially includes
all campaign members. Each person selects a character and marks themselves ready,
or chooses to watch. Changing a character clears readiness. Only the host can
begin, and the server requires every listed person to be ready with at least one
playing character. The host can mark a missing person absent; campaign members
can join/rejoin while the lobby remains open. Joining after the adventure begins
is spectator-only for this short introduction. Readiness persists across refresh
and reconnect; online presence does not silently change it.

Version-one runs retain their original flow and command receipts. Version-two
starter selection reuses each person's already-created template within the run.
No migration is required. Conversation scenes, combat, pause/resume, and the longer
adventure remain planned.

## Conversation follow-up

New version-three introductions continue from the rescue into a second scene with
Mara. Success leaves the party on the road with time to reach the gate; failure
puts them at her camp after dark. The host advances after everyone reads the check
outcome. Playing characters can ask three authored questions about Emberlow, the
river, and Mara's delivery. Friendly conversation needs no dice or AI call. Answers
are shared, attributed, and each topic can be asked once per party.

After at least one question, players discuss their next stop in chat. One playing
character chooses town or river for the party; the first accepted choice commits
the destination. This is an explicit shared decision, not a vote. The ending
reflects both the rescue result and destination, and the host finishes after the
group reads it. The destination is narrative state for now; it does not launch an
additional encounter or update inventory. Questions, answers, the choice, and its
attribution survive refresh and reconnect. Spectators read without choosing.

The introduction is now approximately ten minutes and two scenes. Existing v1/v2
runs retain their original ending and receipt behavior; no migration is required.
Combat, custom actions, pause/resume, and the full 20–30 minute chapter remain next.
