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

- [x] `CLERK_ISSUER` — `https://arriving-escargot-824.clerk.accounts.dev`
- [x] `CLERK_JWKS_URL` — `CLERK_ISSUER` + `/.well-known/jwks.json`
- [ ] `CLERK_AUDIENCE` — not used (no `aud` claim configured)
- [x] Publishable + secret keys — in `web/.env.local`
- [x] Session token customized with `email` + `name` claims ← the load-bearing step
- [x] Invite-only restriction turned on (Access mode → Invite-only; you're an invited user)

Still to do for **production**: a Clerk **Production** instance (own `pk_live_`/
`sk_live_`, custom domain + DNS) with Steps 1–2 re-applied — see `CLERK-SETUP.md`.
The current `pk_test_`/`sk_test_` are a development instance (fine for local + Railway
testing).

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
- **Left:** campaign/session **picker** screens (create/list a campaign, open a
  session, then link into the existing `/table/[sessionId]`). No external setup —
  buildable now; the next step toward MILE-1.

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
