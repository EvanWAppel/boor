# PRIMER — boor

## Next session — 2026-10-24 weekend

**Goal (2 lines).** An AI-assisted D&D table where the campaign continues when a
player is absent: an AI plays their character in their voice, within red lines they set.

**Current state (main @ 2b16904, 2026-10-23).** Live on Railway (service + web +
Postgres, Clerk invite-only dev instance). Rules engine, AI stand-in slice
(guardrails → reasoning → engine → attribution), eval harness, scoped timeline
(DATA-07), the guided v5 adventure (lobby → cart check → Mara → branch check →
two-enemy fight → recap, with proposals, pause/resume, AI guide, free-form bounded
checks) and AI-09 recaps are merged. The weekend run (PR #23, merged 2026-10-23) also
landed SEC-02, SETUP-04 (`scripts/dev.sh`), the guided gap tests, X-02 usage records,
X-01 guided-command logging, the docs reconcile (`NEEDS-FROM-YOU.md` is now historical;
open items live in `BLOCKED.md`) and the CI tidy (`ty check src/ tests/`). No open PRs.
CI on main green after #23.
Baseline on main (measured 2026-10-22, before #23): service `ruff` + `ty` clean, `pytest` all green, 1 skipped (env-gated live-model test), about 15 min with Docker; web
`pnpm test` 17/17, `pnpm lint` clean. #23 added service tests, so the pytest count has grown; re-measure.

**Where to work.** A worktree on a fresh branch off `origin/main`, one branch and
one PR per task. Open PRs; **never merge, never deploy.**

### Autonomous tasks, in order

All seven tasks from the 2026-10-22 primer are done, merged in PR #23:
SEC-02, SETUP-04, guided gap tests, X-02 (slice), X-01 (slice), docs reconcile, CI tidy.

No further autonomous tasks are queued here. Pick the next one from `TASKS.md`,
respecting "Do NOT do" below; everything that needs Evan is in `BLOCKED.md`.

### House rules

- **TDD**: write the failing test first. Service: `uv` only (`uv add`, never hand-edit
  deps). Gate is `uv run ruff check src/ tests/ && uv run ty check src/ tests/ && uv run pytest`
  (pytest needs Docker for testcontainers Postgres). Web gate: `pnpm test && pnpm lint && pnpm build`.
- `web/` is **Next 16 with breaking changes**. Read `web/node_modules/next/dist/docs/`
  before touching Next APIs (web/AGENTS.md).
- LLM reasons, engine adjudicates. The model never supplies dice results, and every
  stand-in action passes `ai.guardrails.check_action`. AI text never becomes canon outcome.
- Service owns all data; web is UI over HTTP/WS. Keep knowledge scoping through
  `boor_service.knowledge` (DATA-07). Never widen what a character can see.
- Game content is SRD 5.1 only (LEGAL.md).
- Verify with tests, curl and logs. **No browser automation.**
- Do not read `.env` / `.env.*` / `web/.env.local`. Read code for variable names.
- Record anything only Evan can resolve in `BLOCKED.md` (🔴/🟡 + exact unblock steps).

### Do NOT do

- **Deploy, merge, or change Railway/Clerk/Anthropic settings** (incl. `ENABLE_STANDINS`).
- **Anything in build-primer §11 (BLOCKED.md "Product/design decisions")**: in-person vs remote, human-DM
  mode (DM-01..05), content sourcing / CONTENT-02 module import, group formation,
  voice economics.
- **AI-12 consequence tiers / G5 consequence deferral**: the thresholds are Evan's call.
- **G5 stand-ins on the guided action system, AI-10 profile learning, GOV-*, ZERO-***:
  each needs product design that Evan confirms (every guided feature so far went through
  a "confirmed by Evan" entry in DECISIONS.md). A written proposal is fine; code is not.
- **SEC-03 web side** (moving the invite token out of the URL path breaks links already
  sent). Evan decides, see BLOCKED.md.
- **GUIDE-02 / MILE-1 / MILE-2 / AI-11 playtests, GUIDE-LAYOUT and VTT-08/09 sign-off**:
  these need humans in a browser.
- Email delivery for recaps (needs a provider account and key).
- VTT-02/03 maps and tokens (deferred by D-04).

---

*(No earlier build handoff existed under this name. The historical handoffs are
`NEEDS-FROM-YOU.md` (historical since 2026-10-24; superseded by `BLOCKED.md`),
`build-primer.md` (product design, canonical) and `GUIDED-PLAY-PLAN.md`.)*
