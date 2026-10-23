# PRIMER — boor

## Next session — 2026-10-24 weekend

**Goal (2 lines).** An AI-assisted D&D table where the campaign continues when a
player is absent: an AI plays their character in their voice, within red lines they set.

**Current state (main @ 1973d9f, 2026-10-22).** Live on Railway (service + web +
Postgres, Clerk invite-only dev instance). Rules engine, AI stand-in slice
(guardrails → reasoning → engine → attribution), eval harness, scoped timeline
(DATA-07), the guided v5 adventure (lobby → cart check → Mara → branch check →
two-enemy fight → recap, with proposals, pause/resume, AI guide, free-form bounded
checks) and AI-09 recaps are merged. No open PRs. The local checkout sits on
`feat/ai-09-recaps`, which is fully merged. Leave it alone.
Baseline on main: service `ruff` + `ty` clean, `pytest` all green, 1 skipped (env-gated live-model test), about 15 min with Docker; web
`pnpm test` 17/17, `pnpm lint` clean.

**Where to work.** A worktree on a fresh branch off `origin/main`, one branch and
one PR per task. Open PRs; **never merge, never deploy.**

### Autonomous tasks, in order

| # | Task | Done when | Test |
|---|------|-----------|------|
| 1 | **SEC-02**: remove the legacy `?token=` WS fallback (`realtime.handle_connection`, line ~410: `header_token or socket.query_params.get("token")`). Keep the log redaction filter (old tabs may still send it). Update the `api.py` docstring and TASKS.md. | A query-string token is rejected (4401-style close) and a test proves it. The subprotocol path is unchanged. | `cd service && uv run pytest tests/test_realtime.py` then the full suite |
| 2 | **SETUP-04**: a one-command local runner for web + service (e.g. `scripts/dev.sh` or a root `Makefile`: service `uvicorn --reload`, web `pnpm dev`, one Ctrl-C stops both). Read env from the existing `.env` files *by path only*. Never open or print them. Document it in README. | One command starts both. `curl localhost:8000/health` returns ok and `curl -I localhost:3000` returns 200. | curl, shellcheck if present |
| 3 | **Guided gap tests** (GUIDED-PLAY-PLAN "Tests and success measures"). The happy paths are already covered (`test_guided_adventure.py` runs town/river through to the recap), so first audit what is missing. Likely gaps: concurrent submissions from two accounts racing on one revision (`asyncio.gather`); an AI-guide decision landing after the session ended or after the scene moved on; a reconnect snapshot mid-fight with a pending roll. Add only the tests that are missing. | The new tests are green. Any bug they surface is fixed TDD in the same PR. | `uv run pytest tests/test_guided*.py` |
| 4 | **X-02 (slice)**: record AI usage per model call (stand-in, adjudicator, recap): model, input/output tokens, latency. Write it as a structured log line, plus a per-session total if it fits the existing models without a migration. Mocked-client tests. | Every model call path emits one usage record, and tests assert it. No key needed. | `uv run pytest -k "usage or standin or recap or adjudicat"` |
| 5 | **X-01 (slice)**: structured logging for guided commands: run id, scene, command, revision, outcome, and rejections with their reason. Never log tokens or prompt text. | caplog-based tests cover one accept and one reject path. | `uv run pytest tests/test_guided*.py` |
| 6 | **Docs reconcile**: `NEEDS-FROM-YOU.md` §2 still shows Railway as `[ ]` (done 2026-09-26), and README "Honest current state" predates guided play and recaps. Fold the still-open items into `BLOCKED.md` (canonical format) and mark NEEDS-FROM-YOU as historical. | Docs agree with TASKS.md, and no open item is lost. | n/a (docs) |
| 7 | **CI tidy**: `ci.yml` still triggers on the dead `data-layer-foundations` branch, and `ty check` covers `src/` only. Drop the branch, and add `ty check tests/` only if it passes cleanly. | CI green on the PR. | GitHub Actions on the PR |

### House rules

- **TDD**: write the failing test first. Service: `uv` only (`uv add`, never hand-edit
  deps). Gate is `uv run ruff check src/ tests/ && uv run ty check src/ && uv run pytest`
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
- **Anything in build-primer §11 / NEEDS-FROM-YOU §6**: in-person vs remote, human-DM
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
`NEEDS-FROM-YOU.md`, `build-primer.md` (product design, canonical) and
`GUIDED-PLAY-PLAN.md`.)*
