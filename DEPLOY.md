# Deploying boor to Railway

Everything is scaffolded to deploy. This is the runbook for the parts only you can
do (create the Railway project, paste secrets). The Dockerfiles, migration release
step, healthchecks, and CORS are already wired and locally verified — see the
"What's already done" section at the bottom.

**Architecture (locked — see `DECISIONS.md`):** one Railway **project** with three
components, co-located:

| Component | Source | Runtime |
| --- | --- | --- |
| **Postgres** | Railway plugin | managed |
| **service** | `/service` (Dockerfile) | FastAPI + Uvicorn on `$PORT` |
| **web** | `/web` (Dockerfile) | Next.js standalone on `$PORT` |

The browser talks to **both** public domains: HTTP/WS to `service`, page loads to
`web`. `service` owns all data; `web` is pure UI.

---

## Order matters

`web`'s build **inlines** the service URL (`NEXT_PUBLIC_API_BASE_URL`) at build
time. So: **deploy `service` first, copy its public domain, then build `web`.**

---

## 1. Create the project + Postgres

1. New Railway project (empty).
2. **+ New → Database → Add PostgreSQL.** Railway exposes it as `${{Postgres.DATABASE_URL}}`.

## 2. Deploy the `service`

1. **+ New → GitHub Repo →** this repo. In the service's **Settings → Root
   Directory**, set **`/service`**. Railway auto-detects `service/railway.json`
   (Dockerfile builder + healthcheck `/health` + the migration pre-deploy step).
2. **Variables** (Settings → Variables):
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`  ← reference, not a literal
   - `CLERK_ISSUER` = `https://<your-clerk-instance>.clerk.accounts.dev`
     (from CLERK-SETUP.md; your **prod** issuer if/when you make a Clerk production instance)
   - `CLERK_JWKS_URL` = `<CLERK_ISSUER>/.well-known/jwks.json`
   - `CORS_ALLOW_ORIGINS` = the `web` public URL, e.g. `https://boor-web.up.railway.app`
     *(set this after step 3 gives you the web domain; comma-separate if more than one)*
   - `CLERK_AUDIENCE` — only if you configure an `aud` claim (currently unused)
   - `ANTHROPIC_API_KEY` — **not needed for MILE-1** (human-DM'd play). Only for the
     AI stand-in, and it trips the personal-key guardrail: mint a **scoped key in a
     dedicated Anthropic workspace with a spend cap** before wiring it — never a
     personal/default key.
3. Deploy. Railway runs `uv run alembic upgrade head` (pre-deploy) then starts
   Uvicorn. Confirm: `curl https://<service-domain>/health` → `{"status":"ok"}`.
4. *(Optional, once)* seed a demo table: run `uv run python -m boor_service.db.seed`
   from the service shell (Railway → service → ⋯ → Shell), or leave it empty.

## 3. Deploy the `web`

1. **+ New → GitHub Repo →** same repo, **Root Directory `/web`** (detects
   `web/railway.json`).
2. **Build-time** variables — these are inlined into the client bundle, so they must
   be set **before/at build** (Railway passes matching service variables to Docker
   `ARG`s):
   - `NEXT_PUBLIC_API_BASE_URL` = the **service** public URL from step 2
     (e.g. `https://boor-service.up.railway.app`) — no trailing slash
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` = your Clerk publishable key (`pk_test_…`
     for now; `pk_live_…` with a prod instance)
3. **Runtime** variable:
   - `CLERK_SECRET_KEY` = your Clerk secret key (`sk_test_…` / `sk_live_…`) — used by
     the auth middleware at runtime, **never** prefixed `NEXT_PUBLIC_`.
4. Deploy, then go back and set the service's `CORS_ALLOW_ORIGINS` to this web
   domain (step 2.2) and redeploy the service so the browser's calls are allowed.
5. Generate a public domain for `web` (Settings → Networking → Generate Domain).

## 4. Smoke-test the live stack

- `curl https://<service-domain>/health` → `{"status":"ok"}`
- Open `https://<web-domain>/` → sign in (Clerk) → you land on **Your campaigns**.
- Create a campaign → open it → **Start a session** → **Enter table**. The table
  connects over WebSocket (Railway supports WS on the service domain).
- Invite yourself with a second email / account to exercise `/invite/<token>`.

---

## Clerk: test vs. production

The current keys are a Clerk **development** instance (`pk_test_`/`sk_test_`), which
works fine on Railway for a private playtest. For a real public launch, create a
Clerk **Production** instance (own `pk_live_`/`sk_live_`, custom domain + DNS) and
re-apply the session-token customization (email/name claims) — see `CLERK-SETUP.md`.

## What's already done (in the repo, locally verified)

- `service/Dockerfile` — uv + Python 3.14; **both images build and boot** (verified:
  `GET /health` → ok, `POST /dice/roll` → real roll, `GET /me` unauthenticated → 401).
- `service/railway.json` — Dockerfile builder, `preDeployCommand:
  ["uv run alembic upgrade head"]`, healthcheck `/health`.
- `web/Dockerfile` + `output: "standalone"` — multi-stage; **image builds and serves
  `/` → 200**. `NEXT_PUBLIC_*` wired as build args.
- `web/railway.json` — Dockerfile builder, healthcheck `/`.
- **CORS** on the service (`CORS_ALLOW_ORIGINS`, defaults to `http://localhost:3000`)
  so the cross-origin browser calls work — the one piece that would otherwise make a
  clean deploy silently fail. Covered by `tests/test_cors.py`.
- `DATABASE_URL` is normalized to `asyncpg` by both the app and Alembic, so Railway's
  stock `postgresql://` URL works as-is.
