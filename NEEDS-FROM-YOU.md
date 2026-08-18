# Things I need from you

The single checklist of steps only **you** can do — external accounts, secrets,
dashboards, and product decisions. Everything buildable without these is already
built and tested (see `TASKS.md` and the git log). Ordered roughly by unblocking
value.

Legend: `[ ]` todo · `[!]` decision needed

---

## 1. Clerk auth — `[ ]`  → full guide in **`CLERK-SETUP.md`**

The service already verifies Clerk JWTs and mirrors users; it just needs a real
Clerk app and its config. The one gotcha that will silently break login:
**customize Clerk's session token to include `email` and `name`** (the service
refuses to mirror a user without an email). Full step-by-step in `CLERK-SETUP.md`.

What I need back from you (or set in the env yourself):
- [ ] `CLERK_ISSUER` — your Clerk Frontend API URL (e.g. `https://<app>.clerk.accounts.dev`)
- [ ] `CLERK_JWKS_URL` — `CLERK_ISSUER` + `/.well-known/jwks.json`
- [ ] `CLERK_AUDIENCE` — *only if* you add an `aud` claim (optional)
- [ ] Publishable + secret keys (for the web app, per `CLERK-SETUP.md`)
- [ ] Session token customized with `email` + `name` claims ← **the load-bearing step**
- [ ] Invite-only restriction turned on (allowlist / restricted sign-ups)

Until these exist, the auth + BFF + WebSocket routes can't be exercised against a
real browser — but they're fully covered by tests using a local keypair, so the
logic is verified.

## 2. Railway hosting + Postgres (DATA-05, SETUP-05) — `[ ]`

Locked architecture: one Railway project — Next.js (Node) + FastAPI service +
Railway Postgres, co-located (see `DECISIONS.md`).

- [ ] Create the Railway project and add a **Postgres** plugin.
- [ ] Deploy the FastAPI service (`service/`); Railway injects `DATABASE_URL`.
- [ ] Set the service env vars there: `DATABASE_URL` (auto), `CLERK_ISSUER`,
      `CLERK_JWKS_URL` (+ `CLERK_AUDIENCE` if used).
- [ ] Run migrations on deploy: `uv run alembic upgrade head` (release step).
- [ ] Optionally seed a demo table once: `uv run python -m boor_service.db.seed`.
- [ ] Object storage for maps/assets (VTT) — pick a bucket (Railway volume or S3-
      compatible) when we get to maps. Not needed yet.

I can write the Railway config / Dockerfile / release command once you've created
the project (or now, as a proposal you approve).

## 3. Web app ↔ service wiring — partly on me `[~]`

- **Done (no keys needed):** a Clerk-agnostic typed client for the whole BFF
  (`web/src/lib/api.ts`) and a session-room WebSocket client (`web/src/lib/ws.ts`),
  plus `web/.env.local.example`. They take an injected `getToken`, so they compile
  and ship today and drop straight onto Clerk once it's set.
- **Left (adds `@clerk/nextjs`, needs your key to boot):** `<ClerkProvider>` +
  `clerkMiddleware`, sign-in/up pages, and passing `useAuth().getToken` into
  `createApiClient`.
- [ ] You: once Clerk (#1) is set, say the word and I'll wire the provider +
      first screens. I held off adding `@clerk/nextjs` so `next build` (and CI)
      stay green without a publishable key.

## 4. CI / GitHub (SETUP-03) — mostly on me `[~]`

- I can add a GitHub Actions workflow running lint + typecheck + tests for the
  service (its tests use testcontainers, which works on GitHub-hosted runners with
  Docker) and lint/build for web.
- [ ] You: nothing required for the service job (no secrets — testcontainers spins
      up its own Postgres). The web build may need a dummy `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
      as a CI secret once Clerk is wired; I'll flag the exact value when we get there.

## 5. Open product decision — `[!]`

- [ ] **D-04 — how minimal is "minimal VTT" for MILE-1?** (see `DECISIONS.md`)
      Realtime transport (VTT-01) is done and is scope-neutral, but the *surface*
      of the first playable table — map + tokens? dice + chat only? initiative
      tracker? — is your call. Tell me the smallest thing your friends would call a
      real session and I'll build to exactly that, resisting scope creep.

---

### What's runnable right now, with zero input from you
- The whole test suite: `cd service && uv run pytest` (real Postgres via testcontainers; Docker must be running).
- The AI stand-in demo (offline, no API key): `uv run python -m boor_service.demo`.
- The stand-in eval scorecard: `uv run python -m boor_service.evals`.
- The rules API (no auth): `uv run uvicorn boor_service.api:app --reload` → `/dice`, `/checks`, `/combat`, `/health`.
