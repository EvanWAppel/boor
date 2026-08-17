# boor

**An AI-assisted Dungeons & Dragons virtual tabletop where the campaign keeps
going even when a player can't make it.** Mark a player absent and an AI plays
their character — in that player's voice, inside limits they set in advance: a
personality profile plus standing "red lines" the AI will not cross.

The interesting part isn't "an LLM plays D&D." It's the *shape* of the thing: a
**bounded LLM actor that takes real actions through a deterministic backend, is
governed by an explicit refusal layer, and is measured by an eval harness.** That
is the full agent lifecycle in one small, legible codebase.

## What this proves (30 seconds)

- **LLM reasons, engine adjudicates.** The stand-in declares *intent* as a
  structured tool call (`attack goblin, +7 to hit, AC 13, 2d6+4`); the
  deterministic 5e rules engine rolls the dice. The model never invents a die
  result — so its actions are as fair as the humans'.
- **A tested, first-class guardrail layer.** Every proposed action is validated
  against the character's standing red lines by a pure, network-free
  `check_action(...)` *before* it can reach the engine. Refusals are structured,
  auditable, and logged.
- **An eval harness for believability + correctness.** Scripted scenarios graded
  on mechanical validity (hard), red-line adherence (hard), and LLM-as-judge
  persona fidelity (soft) → a printed scorecard. Optional LangSmith tracing.
- **Attribution end to end.** Every AI turn — action *or* refusal — is persisted
  to the session timeline flagged `ai_generated=True`.
- **Honest failure modes.** The design doc names where the agent breaks (latency,
  model-supplied modifiers, self-reported risk, red-line coverage gaps, persona
  drift, judge noise) and the mitigation for each.

## Watch it take a turn

```bash
cd service
uv run python -m boor_service.demo
```

Plays a short encounter and streams each turn: the scene, the stand-in's
in-character action, the engine's dice result, and — on a charmed ally it's
tempted to strike — the guardrail refusing the action before the engine ever
rolls. Runs offline with a scripted reasoner (zero setup); set
`ANTHROPIC_API_KEY` to drive it with the live model. Either way the guardrail and
rules engine are the real ones.

## How the agent is built

Three responsibilities, three components, no overlap:

| Concern | Owner |
| --- | --- |
| *What should the character do?* | the LLM (`boor_service.ai.standin`) |
| *What actually happens?* | the rules engine (`boor_service.mechanics` / `dice` / `combat`) |
| *Is the character allowed to do this?* | the guardrail (`boor_service.ai.guardrails`) |

The full design — the tool schema, red-line enforcement, the eval methodology,
and the candid failure-modes section — lives in
**[`service/src/boor_service/ai/README.md`](service/src/boor_service/ai/README.md)**.

## Architecture

A **Next.js** web client (`web/`) over a **Python FastAPI** rules-and-AI service
(`service/`), with an async **SQLAlchemy 2.0 / Postgres** data layer and Alembic
migrations. The service owns all data (a backend-for-frontend); the web app is
pure UI over HTTP/WebSocket. Decisions and their rationale are in
[`DECISIONS.md`](DECISIONS.md).

Engineering hygiene: `uv` + `pytest` + `ruff` + `ty`, a 150+-test suite,
deterministic dice under a seeded RNG, and no swallowed errors — model and tool
failures surface loudly.

## Honest current state

- **Real and tested:** the 5e SRD rules engine, the AI stand-in slice (guardrails
  → reasoning → adjudication → attribution), the eval harness, and the data layer
  (users, campaigns, invites, sessions, unified event timeline).
- **Not built yet:** the playable tabletop UI (the web app is still close to the
  Next.js scaffold), realtime transport, and auth wiring. This is an after-hours
  project; the agent slice is the part that's finished.

The task breakdown and phase plan are in [`TASKS.md`](TASKS.md); the product
vision in [`prd.md`](prd.md).

## Repository layout

| Path | What |
| --- | --- |
| `service/` | FastAPI rules-and-AI service — the engine, the AI stand-in, the evals ([README](service/README.md)) |
| `service/src/boor_service/ai/` | the agent: pure domain types, the guardrail, the stand-in ([design doc](service/src/boor_service/ai/README.md)) |
| `web/` | Next.js web client (scaffold) |

## Content & license

All game content is **SRD 5.1 (CC BY 4.0)** only — the engine is mechanics, no
proprietary IP. See [`LEGAL.md`](LEGAL.md) for the attribution notice and the
content-scope boundary.
