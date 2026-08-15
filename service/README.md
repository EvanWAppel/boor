# boor-service

Python AI / game-logic service for **boor** (see `../prd.md`). Owns the 5e SRD
rules engine, AI stand-in + AI DM reasoning, personality profiles, and campaign
memory. The Next.js web app (`../web`) talks to this service.

Game content is SRD 5.1 (CC-BY-4.0) only — see `../LEGAL.md` for the required
attribution and content-scope boundary.

## Toolchain

- **uv** for env + deps (`uv add LIB`, `uv add --dev LIB` — never edit
  `pyproject.toml` deps by hand)
- **pytest** for TDD
- **ruff** for lint, **ty** for typechecks

## Common commands

```bash
uv run pytest        # run tests
uv run ruff check .  # lint
uv run ty check      # typecheck
```

## Running the API

A thin FastAPI surface (`boor_service.api`) exposes the rules engine over HTTP —
no persistence or auth yet (those wait on the datastore/auth decisions in
`../DECISIONS.md`).

```bash
uv run uvicorn boor_service.api:app --reload   # http://127.0.0.1:8000
# interactive docs at /docs
```

Routes: `GET /health`, `POST /dice/roll`, `POST /dice/d20`,
`POST /checks/ability|skill|save`, `POST /combat/attack|damage`. Bad input
(malformed notation, out-of-range score) returns HTTP 400 with the engine's
error message; missing/mistyped fields return 422.

## Modules

- `boor_service.dice` — 5e dice engine (RULES-01): notation parsing, d20 with
  advantage/disadvantage. Deterministic when a seeded RNG is injected.
- `boor_service.api` — FastAPI HTTP layer over the engine (SETUP-02).
