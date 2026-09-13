# Clerk setup — do this tomorrow

This is the **manual, account-and-dashboard** half of auth (D-03). The **service
half is already built and tested** — `boor_service.auth` verifies Clerk JWTs
against your JWKS and mirrors each user on first login. Your job tomorrow is to
create the Clerk app, make its tokens carry the claims the service needs, and wire
the Next.js app to sign users in and forward the token.

> **The one thing that will bite you:** Clerk's default session token contains
> `sub` but **not** `email`. The service *requires* `email` to create a user
> (`repository.sync_user` raises without it). **Step 2 fixes this — don't skip it.**

---

## What the service already expects

| Env var (service) | Purpose | Example |
|---|---|---|
| `CLERK_ISSUER` | Must equal the `iss` claim in the token | `https://your-app.clerk.accounts.dev` |
| `CLERK_JWKS_URL` | Clerk's public keys (RS256) | `https://your-app.clerk.accounts.dev/.well-known/jwks.json` |
| `CLERK_AUDIENCE` | *Optional.* Only set if you configure an `aud` claim | `boor-api` |

Built from these in `service/src/boor_service/auth/clerk.py → verifier_from_env()`.
Verification is RS256 against the JWKS; **no Clerk secret key lives in the
service.** The token's `sub` becomes the user's `clerk_user_id`; the `email` and
`name` claims populate the mirrored `User` row.

---

## Step 1 — Create the Clerk application (invite-only)

1. Sign up / log in at **clerk.com** → **Create application**.
2. Name it (e.g. `boor`), enable the sign-in methods you want (email + Google is fine).
3. Make it **invite-only** (this is the product requirement):
   - **User & Authentication → Restrictions** → turn on **Allowlist** (or
     **Restrict sign-ups**), so only invited emails can create accounts.
   - You'll add players' emails here (or via Clerk **Invitations**) as you onboard
     friends. *(App-level campaign invites are separate — that's the service's
     invite/accept flow.)*

## Step 2 — Make tokens carry `email` and `name` (CRITICAL)

The service needs these claims. In the Clerk dashboard:

1. Go to **Sessions → Customize session token** (a.k.a. the session-token claims editor).
2. Set the claims to include:
   ```json
   {
     "email": "{{user.primary_email_address}}",
     "name": "{{user.full_name}}"
   }
   ```
3. Save.

That's it — no separate JWT template is required if you customize the default
session token. (If you prefer a **named JWT template** instead, create one with the
same two claims and have the web app request the token by that template name in
Step 5. Either works; the service only cares that `email`/`name` are present.)

> If you later want to rename these claims, they're configurable in
> `ClerkVerifier(..., email_claim=..., name_claim=...)` — but matching the defaults
> (`email`, `name`) means zero code changes.

## Step 3 — Grab the issuer, JWKS URL, and keys

- **Issuer / Frontend API URL:** **API Keys** (or **Domains**) → your Frontend API
  domain, e.g. `https://your-app.clerk.accounts.dev`. That's `CLERK_ISSUER`.
- **JWKS URL:** `CLERK_ISSUER` + `/.well-known/jwks.json`.
- **Publishable key** (`pk_test_…`) and **Secret key** (`sk_test_…`): **API Keys**.

Confirm the issuer by decoding a real token (paste into jwt.io) and checking `iss`
matches exactly — a trailing-slash mismatch is the usual gotcha.

## Step 4 — Set the service env vars

The service reads these from the **process environment** — it does **not** auto-load
`service/.env` (there's no `load_dotenv`). So `export` them in your shell, prefix the
command inline, or run `uv run --env-file .env uvicorn …`. A bare `.env` file alone
does nothing.

```bash
export CLERK_ISSUER="https://your-app.clerk.accounts.dev"
export CLERK_JWKS_URL="https://your-app.clerk.accounts.dev/.well-known/jwks.json"
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"   # a REAL URL, never "..."
# export CLERK_AUDIENCE=...   # only if you added an aud claim
```

`DATABASE_URL` must be a real, parseable Postgres URL (the auth routes hit Postgres);
a placeholder like `...` or an empty value throws `sqlalchemy ArgumentError` at engine
creation and every authed route 500s **before** the token is checked. The rules
endpoints (`/dice`, `/checks`, `/combat`) stay open and need none of this.

Apply the schema before first use (and after pulling new migrations):

```bash
uv run alembic upgrade head    # requires DATABASE_URL to be set/exported
```

The same three vars go into Railway's **service** variables later.

## Step 5 — Wire the Next.js app (`web/`) — ✅ DONE

`@clerk/nextjs` (v7, "Core 3") is installed and wired. The one manual bit left is
env vars (below). What's wired, and two version gotchas that bit us:

1. **SDK installed:** `@clerk/nextjs@7.x` (`cd web && pnpm add @clerk/nextjs`).
2. **Middleware is `web/src/proxy.ts`, not `middleware.ts`.** Next.js 16 renamed
   `middleware` → **proxy** (`middleware.ts` still works but is deprecated). Clerk's
   own rule: `proxy.ts` on Next 16+, `middleware.ts` on 15 and below — same body
   (`export default clerkMiddleware()`).
3. **`<Show when="…">`, not `<SignedIn>/<SignedOut>`.** Clerk Core 3 removed the
   `<SignedIn>`, `<SignedOut>`, and `<Protect>` components — they now *throw at build
   time* — in favour of a single `<Show when="signed-in|signed-out">` (with an
   optional `fallback`). `ClerkProvider`, `SignInButton`, `SignUpButton`,
   `UserButton`, and `useAuth()` are unchanged. `<ClerkProvider>` goes **inside
   `<body>`** in `web/src/app/layout.tsx`.
4. **Everything is gated on `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`** (a build-time
   constant). Key present (Railway, local `.env.local`) → full Clerk. Key absent
   (CI's `pnpm build`, or before you add `.env.local`) → the app falls back to the
   dev-token seam so CI stays green. The single swap point is `web/src/lib/auth.ts`
   (`useToken()` → `useAuth().getToken`); `api.ts` / `ws.ts` already forward the
   token as a `Bearer` header, so no other files change.
5. **Web env vars** — create `web/.env.local` (secret key is server-only, never
   `NEXT_PUBLIC_`):
   ```bash
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="pk_test_..."
   CLERK_SECRET_KEY="sk_test_..."
   NEXT_PUBLIC_API_BASE_URL="http://localhost:8000"   # the FastAPI service (or its Railway URL)
   ```
   No JWT template name is needed: `getToken()` returns the *default* session token,
   which now carries `email`/`name` from Step 2.

## Step 6 — Verify end-to-end

1. Start the service (with the vars **exported** from Step 4 — do not paste literal
   `...`; that's what makes every authed route 500):
   ```bash
   cd service && uv run uvicorn boor_service.api:app --reload
   ```
2. Sign in on the web app, grab a token (log it, or copy from the network tab).
3. Hit the service directly:
   ```bash
   curl -H "Authorization: Bearer <token>" http://localhost:8000/me
   ```
   - **200** with your `email` → auth works end-to-end. 🎉
   - **401 "cannot mirror a new user without an email"** → Step 2 wasn't applied
     (token has no `email` claim).
   - **401 "token verification failed"** → `CLERK_ISSUER`/`CLERK_JWKS_URL` mismatch,
     or the token expired.
4. Then try the real flow: `POST /campaigns` → `POST /campaigns/{id}/invites` →
   `POST /invites/{token}/accept` (as a second user) → `GET /campaigns/{id}/members`.

---

## Reference: the auth endpoints now live

All require `Authorization: Bearer <clerk-token>`:

- `GET /me` — your mirrored account
- `POST /campaigns` · `GET /campaigns` — create / list-mine (creator becomes DM)
- `GET /campaigns/{id}/members` — roster (any member)
- `POST /campaigns/{id}/invites` — invite by email (**DM only**)
- `POST /invites/{token}/accept` — join a campaign
- `POST|GET /campaigns/{id}/characters`, `GET /characters/{id}` — characters (members)
- `PUT|GET /characters/{id}/profile`, `POST|GET /characters/{id}/red-lines` —
  stand-in persona + red lines (**the character's player or the DM** may edit)

## Gotchas checklist

- [ ] Session token customized with `email` **and** `name` (Step 2) — the #1 failure.
- [ ] `CLERK_ISSUER` matches the token's `iss` **exactly** (no trailing slash drift).
- [ ] `CLERK_SECRET_KEY` is server-only; only the publishable key is `NEXT_PUBLIC_`.
- [ ] Invite-only restriction is on, so random sign-ups can't create accounts.
- [ ] Clock skew: the verifier allows 30s leeway; larger drift will reject tokens.
- [ ] Next 16: middleware lives in `proxy.ts` (not `middleware.ts`).
- [ ] Clerk Core 3: use `<Show when=…>` (not `<SignedIn>/<SignedOut>`, which now throw).
- [ ] `pk_test_`/`sk_test_` are a **Development** instance. A real shared Railway URL
      eventually needs a **Production** instance (own `pk_live_`/`sk_live_`, custom
      domain + DNS) with Steps 1–2 re-applied. Dev keys work for testing meanwhile.
