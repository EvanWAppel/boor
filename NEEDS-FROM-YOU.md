# Things I need from you

The single checklist of steps only **you** can do — external accounts, secrets,
dashboards, and product decisions. Everything buildable without these is already
built and tested (see `TASKS.md` and the git log). Ordered roughly by unblocking
value.

Legend: `[ ]` todo · `[!]` decision needed

---

## 1. Clerk auth — `[x]` ✅ DONE (verified live)  → guide in **`CLERK-SETUP.md`**

The Clerk app is created and fully wired: signed-in `GET /me` returns **200** with
the mirrored user (`email` + `display_name`). Config now lives in `service/.env`
(local dev) and `web/.env.local`.

- [x] `CLERK_ISSUER` — `https://<your-clerk-instance>.clerk.accounts.dev` (real value in `service/.env`)
- [x] `CLERK_JWKS_URL` — `CLERK_ISSUER` + `/.well-known/jwks.json`
- [ ] `CLERK_AUDIENCE` — not used (no `aud` claim configured)
- [x] Publishable + secret keys — in `web/.env.local`
- [x] Session token customized with `email` + `name` claims ← the load-bearing step
- [x] Invite-only restriction turned on (Access mode → Invite-only; you're an invited user)

Still to do for **production**: a Clerk **Production** instance (own `pk_live_`/
`sk_live_`, custom domain + DNS) with Steps 1–2 re-applied — see `CLERK-SETUP.md`.
The current `pk_test_`/`sk_test_` are a development instance (fine for local + Railway
testing).

## 2. Railway hosting + Postgres (DATA-05, SETUP-05) — `[ ]`  → **full runbook in `DEPLOY.md`**

**Scaffolding is done and locally verified** — Dockerfiles for both services, the
migration release step, healthchecks, and CORS are all written. Both images
**build and boot** on my machine (`service` → `/health` ok + a real dice roll +
`/me` 401; `web` → `/` 200). What's left is the parts only you can do:

- [ ] Create the Railway project and add a **Postgres** plugin.
- [ ] Add the **service** (root dir `/service`) — `railway.json` auto-runs
      `alembic upgrade head` on deploy and healthchecks `/health`. Set vars:
      `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `CLERK_ISSUER`, `CLERK_JWKS_URL`,
      and `CORS_ALLOW_ORIGINS` = the web URL (step below).
- [ ] Add the **web** (root dir `/web`) — set **build-time** `NEXT_PUBLIC_API_BASE_URL`
      (= the service URL) + `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, and **runtime**
      `CLERK_SECRET_KEY`. Deploy service first so you have its URL.
- [ ] Back-fill the service's `CORS_ALLOW_ORIGINS` with the web domain, redeploy.
- [ ] Optionally seed a demo table once: `uv run python -m boor_service.db.seed`.
- ⚠️ **`ANTHROPIC_API_KEY` is NOT needed for MILE-1** (human-DM'd). It's only for
  the AI stand-in and it hits the personal-key guardrail — mint a scoped key in a
  dedicated capped Anthropic workspace before wiring it, never your personal key.
- [ ] Object storage for maps/assets (VTT) — not needed until maps (post-MILE-1).

**Every step, with exact values, is in `DEPLOY.md`.**

## 3. Web app ↔ service wiring — partly on me `[~]`

- **Done (no keys needed):** the Clerk-agnostic typed client (`web/src/lib/api.ts`,
  now incl. dice + session endpoints), the session-room WS client
  (`web/src/lib/ws.ts`, incl. `sendOoc`/`sendRoll`), and **the whole
  theater-of-the-mind table** (D-04): `web/src/app/table/[sessionId]/` +
  `web/src/components/table/*` — shared log, IC/OOC composer, dice roller wired to
  the rules engine, DM initiative tracker, presence, read-only party sheets, over a
  `useRoom` hook that replays history and dedupes live frames. **`pnpm lint` +
  `next build` green.** Auth flows through one seam (`web/src/lib/auth.ts`).
- **⚠️ Verification gap:** the table is **compile-verified only** — I can't exercise
  it end-to-end without a browser (per your no-browser rule) *and* it needs a real
  token + a running service. To smoke-test it yourself before Clerk: run the service,
  mint a Clerk-shaped JWT, set `NEXT_PUBLIC_DEV_TOKEN` (or
  `localStorage["boor_dev_token"]`), and open `/table/<session-id>`.
- **Done (Clerk wired):** `@clerk/nextjs` + `<ClerkProvider>` + `<Show>` header
  (sign-in/up + user button) + Next 16 `proxy.ts` (`clerkMiddleware`), and the dev
  token in `auth.ts` swapped for `useAuth().getToken` (gated on the publishable key
  so keyless CI builds stay green). Verified: signed-in `/me` → 200.
- **Done (the front door — NAV-01):** the whole navigation flow now exists so a
  signed-in user has somewhere to go: home (`/`) shows your campaigns + a create
  form; `/campaigns/[id]` is the campaign hub (start/end sessions as DM, enter any
  session → the existing `/table/[sessionId]`, the roster with a DM invite form that
  mints a copyable `/invite/[token]` link, and characters with a minimal
  create-a-PC form); `/invite/[token]` redeems an invite and lands the player in the
  campaign. `pnpm lint` + `next build` green; the backing API flow is covered by the
  service suite (33 API tests green on real Postgres). Compile/typecheck-verified in
  the browser sense (no-browser rule) — the last live gap is running it on Railway.
- **Left toward MILE-1:** nothing *buildable without you* — the code path from
  sign-in → campaign → session → live table is complete. What remains is **deploy**
  (§2 Railway) so friends can actually reach it, and optionally invite **email
  delivery** (today the DM copies the link and sends it themselves).

## 4. CI / GitHub (SETUP-03) — mostly on me `[~]`

- I can add a GitHub Actions workflow running lint + typecheck + tests for the
  service (its tests use testcontainers, which works on GitHub-hosted runners with
  Docker) and lint/build for web.
- [ ] You: nothing required for the service job (no secrets — testcontainers spins
      up its own Postgres). The web build may need a dummy `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
      as a CI secret once Clerk is wired; I'll flag the exact value when we get there.

## 5. Open product decision — `[!]`

- [x] **D-04 — how minimal is "minimal VTT" for MILE-1?** ✅ RESOLVED —
      theater-of-the-mind (see `DECISIONS.md`). Kept here for the record.

## 6. Decisions from the build primer — `[!]`

New canonical design docs landed (`build-primer.md` + `the-ninth-toll.md`). They
confirm the locked architecture and the north-star bet, but raise decisions that
are explicitly **yours** — the primer says "do not silently resolve an OPEN item."

**Two conflicts with the current plan (resolve first — they change scope):**
- [!] **Module ingestion.** Primer §3 forbids building an ingestion pipeline for
      published adventure PDFs ("the single largest legal risk"), yet `CONTENT-02`
      in `TASKS.md` is exactly that. The primer wants **original in-house campaigns
      only**. Kill `CONTENT-02`, or keep it and accept the legal exposure? (Primer
      says this specific question "warrants review by actual counsel.")
- [!] **Content sourcing.** `DECISIONS.md` says "authored + imported + AI-generated";
      primer says original-only. Pick one so the content pipeline (Phase 4) is built
      to the right target.

**The five OPEN items from primer §11 (do not resolve unilaterally):**
- [!] **In-person vs. remote for v1.** Primer recommends remote-first (you own the
      whole channel); in-person is a hardware/vibe problem. Founder's call.
- [!] **Human-DM mode.** Currently undesigned; primer recommends AI-DM-only for v1.
      (Note: `TASKS.md` Phase 3 DM-04 assumes swappable human/AI DM — revisit.)
- [!] **Unit economics.** Voice-first (4hr × transcription × DM agent × N persona
      agents) may be unaffordable for hobbyists — may force text/async-first. Run the
      cost model before committing to voice.
- [!] **Group formation.** Beginners lack four friends on a schedule (the real
      barrier); matchmaking is a second product. "Bring your own group" vs.
      matchmaking — decide deliberately.
- [!] **Consequence-tier thresholds (§7.3).** Needs concrete numbers (how much lost
      party resource trips the gate, etc.) before the tier logic can be built.

---

### What's runnable right now, with zero input from you
- The whole test suite: `cd service && uv run pytest` (real Postgres via testcontainers; Docker must be running).
- The AI stand-in demo (offline, no API key): `uv run python -m boor_service.demo`.
- The stand-in eval scorecard: `uv run python -m boor_service.evals`.
- The rules API (no auth): `uv run uvicorn boor_service.api:app --reload` → `/dice`, `/checks`, `/combat`, `/health`.
