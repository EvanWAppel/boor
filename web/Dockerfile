# syntax=docker/dockerfile:1

# boor Next.js web client (SETUP-05). Multi-stage build → standalone runtime.
#
# IMPORTANT: NEXT_PUBLIC_* values are inlined at BUILD time, so they must be
# passed as build args (on Railway: set them as *build-time* variables on this
# service). CLERK_SECRET_KEY is used by the middleware at RUNTIME, so it's a
# normal runtime variable, not a build arg.

FROM node:22-alpine AS base
ENV PNPM_HOME="/pnpm" PATH="/pnpm:$PATH"
RUN corepack enable

# --- dependencies -----------------------------------------------------------
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
# --ignore-scripts: skip dependency postinstall/build scripts (the only one here is
# unrs-resolver, an ESLint-only native dep) so a non-interactive install can't fail
# on pnpm's ignored-builds guard. Next's native bits ship as prebuilt platform
# packages, not build scripts, and the app's own `pnpm build` runs as its own step.
# Keep this portable across Railway services; dependency layers are still cached.
RUN pnpm install --frozen-lockfile --ignore-scripts

# --- build ------------------------------------------------------------------
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Public config, inlined into the client bundle at build time.
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY \
    NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# --- runtime ----------------------------------------------------------------
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

# Standalone output: the server + only the traced node_modules it needs.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
# Next's standalone server reads PORT/HOSTNAME; Railway overrides $PORT at runtime.
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
