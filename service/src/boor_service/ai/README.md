# The boor AI stand-in

When a player can't make a session, an AI plays their character — in that
player's voice, inside limits they set in advance. This module is that agent.

It is deliberately small and legible, because the point is not "an LLM plays
D&D" — it's the *shape* of the thing: **a bounded LLM actor that takes real
actions through a deterministic backend, is governed by an explicit refusal
layer, and is measured by an eval harness.** This README is the design doc for
that agent: how it's put together, what each seam protects, and — candidly —
where it breaks.

---

## The core split: LLM reasons, engine adjudicates, guardrail governs

Three responsibilities, three components, no overlap:

| Concern | Who owns it | Why it's separated |
| --- | --- | --- |
| *What should the character do?* | the LLM (`standin.py`) | judgment, voice, tactics — the fuzzy part |
| *What actually happens?* | the rules engine (`mechanics`, `dice`, `combat`) | dice, hit/miss, damage — must be deterministic and fair |
| *Is the character allowed to do this?* | the guardrail (`guardrails.py`) | player-set red lines — must be auditable, no model in the loop |

The model **never invents a die result.** It declares *intent* as a structured
tool call ("attack goblin, my bonus is +7, its AC is 13, damage 2d6+4"); the
engine rolls. This is the load-bearing design decision — it's what makes the
agent's actions *fair* (the same RNG the human players use, injectable and seedable
under test) rather than a language model asserting outcomes it likes.

```
                  ┌─────────────────────────────────────────────┐
  persona +       │  standin.decide_action                      │
  red lines +     │                                             │
  timeline   ───► │  1. Claude  ──tool_call──►  _to_action      │
                  │                                 │            │
                  │  2. guardrails.check_action  ◄──┘            │
                  │        │                                     │
                  │     Refused ──► StandInDecision(allowed=     │
                  │        │              False, refusal=…)      │
                  │      Allowed                                 │
                  │        │                                     │
                  │  3. engine (_dispatch) ──► StandInDecision   │
                  └─────────────────────────────────────────────┘
                                   │
                    act_on_turn ──►│──► SessionEvent(ai_generated=True)
```

Every proposed action is checked *before* it reaches the engine. A red-lined
action is refused and never rolled.

---

## The tool schema

The model is given exactly four tools (`ACTION_TOOLS` in `standin.py`), each a
thin wrapper over the engine or the timeline:

| Tool | Wraps | Dice? |
| --- | --- | --- |
| `attack` | `mechanics.attack_roll` + `mechanics.roll_damage` | yes (to-hit, then damage on hit; doubled on a crit) |
| `ability_check` | `mechanics.ability_check` | yes (d20 + bonus vs DC) |
| `speak` | timeline only | no |
| `move` | timeline only | no |

`tool_choice` is `auto` and the model must pick exactly one. Reasoning uses
adaptive extended thinking on `claude-opus-4-8` (see the `claude-api` reference
for the model id). The `attack` and `move` tools also ask the model to self-label
a `self_risk` of `none` / `risky` / `lethal`, which the guardrail can act on
(see failure modes — this is a self-reported signal).

The Anthropic client is **injected** via the `SupportsMessages` structural
protocol — exactly the injectable-RNG pattern the rules engine already uses. Unit
tests pass a fake with the same shape and assert on the emitted tool call; one
env-gated test hits the live API. No network is hard-wired into the logic.

---

## The guardrail / refusal layer

`guardrails.check_action(action, red_lines, game_state) -> Allowed | Refused` is
a **pure, deterministic, network-free** function. That is the whole point: red
lines are governance, and governance you can't test in isolation isn't worth
much. Red lines are *structured*, not free text, so the check is auditable
without a model:

- `no_attacking_allies` — no offensive action against an `ally`
- `no_attacking_the_helpless` — no offensive action against an unconscious target
- `no_targeting_named` — never target specific entity ids (e.g. "never hurt the king")
- `no_lethal_self_risk` — no action the model labeled `lethal` self-risk
- `forbid_action_types` — block whole action categories

Red lines are evaluated in order; the **first** violation wins, so the result is
deterministic for a fixed input. The player's own phrasing lives in `RedLine.note`
and is echoed into the refusal reason, so the timeline reads
`declined to attack: would take an offensive action against ally Lyra (red line:
"never attack a party member")`.

Refusals are not errors. A refused action returns a `StandInDecision` with
`allowed=False`; `act_on_turn` still persists it to the timeline with
`ai_generated=True`, so the log shows the AI acted *and* why it declined.

---

## Attribution

`act_on_turn` is the persistence seam. Every stand-in outcome — action **or**
refusal — becomes a `SessionEvent` with `ai_generated=True` (task AI-08). A human
reading the story log can always tell which turns the AI drove and, on refusals,
what line it wouldn't cross. `event_payload` captures a JSON-safe record of the
tool call and the engine's numbers (to-hit total, hit/crit flags, damage, check
result) for audit and replay.

---

## The eval harness

`boor_service.evals` answers the question agent roles actually screen for: *can
you evaluate and tune this thing on real tasks?* Run it with
`uv run python -m boor_service.evals`.

Each scenario (`scenarios.py`) is a fixed game state + persona the stand-in must
act in; some carry a `RedLineTrap` — a tempting-but-forbidden action an aligned
model should avoid *on its own*. Three graders (`graders.py`):

| Grader | Kind | Asserts |
| --- | --- | --- |
| `mechanical_validity` | **hard** | the action is legal for the scene (target exists, not self) |
| `red_line_adherence` | **hard** | the model didn't even *propose* the trap action |
| `persona_fidelity` | **soft** | LLM-as-judge scores "does this read like the character?" vs a threshold |

The split matters. `red_line_adherence` deliberately grades the *model's
proposal*, not the guardrail's verdict — the guardrail is the safety net, but a
good stand-in shouldn't need it. A scenario where the guardrail blocked the action
but the model still tried it is a **failure**, and the detail says so. Judge
failures (a refusal, malformed JSON) surface loudly rather than silently scoring
zero — a broken judge is a broken eval, not a failing character.

`runner.py` seeds the engine RNG per scenario, so a run is reproducible; a
scenario that produces no action at all is recorded as a hard failure rather than
aborting the suite. Optional LangSmith tracing (`tracing.py`) can be flipped on to
inspect individual runs.

---

## Failure modes (and what we do about them)

Honest section. This is where the agent breaks, and where the next work is.

**Latency can stall a live table.** Adaptive thinking on Opus takes seconds; a
real session can't wait indefinitely on one absent player's turn. There is no
timeout / fallback-action budget yet — that's task AI-07. Today the call is
synchronous and unbounded. Mitigation is designed but not built: a latency budget
with a safe default action (`dodge` / `speak` a hedge) on timeout.

**The model can propose an illegal or nonsensical action.** It supplies its own
`attack_bonus`, `target_ac`, and `damage` — these are *not* yet derived from the
`Character` sheet, so a confused model could low-ball an AC or cite a weapon it
doesn't have. The engine adjudicates the roll fairly, but it trusts those inputs.
`mechanical_validity` catches gross errors (attacking a nonexistent target or
itself); it does not yet cross-check modifiers against the sheet. Next step:
compute attack/damage from the `Character` model and pass the model only the
target, so it can't fabricate its own bonuses.

**`self_risk` is self-reported.** `no_lethal_self_risk` depends on the model
honestly labeling its own action as `lethal`. A mistaken or adversarial model that
labels a suicidal leap `none` bypasses that specific red line. This is why the
eval's `red_line_adherence` grader tests the *proposal* — we measure whether the
model walks into the trap, not just whether the net catches it. Structured red
lines (`no_attacking_allies`, `no_targeting_named`) don't have this weakness
because they're checked against objective scene state, not a model self-rating.

**Red-line coverage has gaps.** `check_action` only protects entities present in
`game_state.entities` — unknown target ids are skipped (`_targets`). If the scene
state handed in is incomplete, protection is incomplete. And the free-text
`RedLine.note` a player writes is *not* enforced — only the five structured kinds
are. A player who writes "never betray the party's trust" gets a note in the log,
not a guarantee. Closing this means either expanding the structured vocabulary or
adding an LLM-based semantic red-line check (with its own reliability caveats).

**Persona drift.** Over a long session the character can flatten toward a generic
"brave adventurer." `persona_fidelity` is the early-warning signal; the durable
fix (task AI-10) is refining the persona from that character's own session history
rather than a static profile.

**Judge unreliability.** LLM-as-judge is noisy and can be gamed by fluent-but-off
prose. We treat it as a soft, thresholded signal (not a hard gate), assert judge
errors loudly, and keep the deterministic graders as the real safety guarantees.
Persona scores are for *tuning*, not for *blocking* an action.

---

## Map to the code

| File | Role |
| --- | --- |
| `actions.py` | pure domain types (`ProposedAction`, `GameState`, `Entity`, enums) — no DB, no network |
| `guardrails.py` | `check_action` — the pure refusal layer |
| `standin.py` | `decide_action` / `act_on_turn` — model call, tool dispatch, engine adjudication, attribution |
| `../evals/` | scenarios, graders, runner, scorecard, optional tracing |

Tests: `tests/test_guardrails.py`, `tests/test_standin.py`, `tests/test_evals.py`
(model mocked; one env-gated live test).
