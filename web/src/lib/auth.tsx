// Auth seam for the web app — the single place the token comes from.
//
// The whole app takes its bearer token through `useToken()`, which returns a stable
// `getToken` for `createApiClient` / `connectSessionRoom`. The root layout mounts
// exactly one session provider per request:
//
//   • demo host (PLAT-DEMO-01) → <DemoAuthSession>: no Clerk at all; this browser's
//     guest token (`demo.<id>`, see src/lib/demo.ts), which the service accepts only
//     from the demo origin and only for its sandbox.
//   • Clerk key present (Railway, local web/.env.local) → <ClerkAuthSession>, inside
//     <ClerkProvider>: Clerk's `useAuth().getToken`, returning the customized session
//     token that carries the `email`/`name` claims the service requires (CLERK-SETUP.md).
//   • key absent (CI's `pnpm build`, or before Clerk is wired locally) →
//     <DevAuthSession>: a dev token from localStorage/env, so pages compile and CI
//     stays green without a key.
//
// Each provider calls its own hooks unconditionally, so the rules of hooks hold.

"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { useAuth } from "@clerk/nextjs";

import type { TokenGetter } from "./api";
import { guestToken } from "./demo";

/** localStorage key a developer can set to a minted token for local testing. */
export const DEV_TOKEN_KEY = "boor_dev_token";

/** Read the current dev token, if any (localStorage takes precedence over env). */
export function readDevToken(): string | null {
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem(DEV_TOKEN_KEY);
    if (stored) return stored;
  }
  return process.env.NEXT_PUBLIC_DEV_TOKEN ?? null;
}

/** Auth readiness + identity, provider-agnostic. */
export interface AuthSession {
  /** Stable getter for the bearer token (null when signed out / no dev token). */
  getToken: TokenGetter;
  /** False until the auth provider has resolved the current session. */
  isLoaded: boolean;
  /** Whether there is a signed-in user (or a dev token / demo guest). */
  isSignedIn: boolean;
  userId: string | null;
  /** True on the public demo host: a sandboxed guest, not a real account. */
  isDemo: boolean;
}

const AuthSessionContext = createContext<AuthSession | null>(null);

/** Clerk-backed session — the real path once a publishable key is set. */
export function ClerkAuthSession({ children }: { children: ReactNode }) {
  const { getToken, isLoaded, isSignedIn, userId } = useAuth();
  const value = useMemo(
    () => ({
      getToken,
      isLoaded,
      isSignedIn: Boolean(isSignedIn),
      userId: userId ?? null,
      isDemo: false,
    }),
    [getToken, isLoaded, isSignedIn, userId],
  );
  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

/** Dev-token session — used in CI/builds and before Clerk is wired locally. */
export function DevAuthSession({ children }: { children: ReactNode }) {
  const getToken = useCallback(() => readDevToken(), []);
  // Dev token is resolved once at load; readiness is immediate.
  const value = useMemo(
    () => ({ getToken, isLoaded: true, isSignedIn: Boolean(readDevToken()), userId: "dev", isDemo: false }),
    [getToken],
  );
  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

/** Demo guest session — the demo host; never touches Clerk. */
export function DemoAuthSession({ children }: { children: ReactNode }) {
  // Tokens are only requested from effects/handlers, so window is always present.
  const getToken = useCallback(() => guestToken(window.localStorage), []);
  const value = useMemo(
    () => ({ getToken, isLoaded: true, isSignedIn: true, userId: "guest", isDemo: true }),
    [getToken],
  );
  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

/** The current auth session, from whichever provider the root layout mounted. */
export function useAuthSession(): AuthSession {
  const session = useContext(AuthSessionContext);
  if (!session) throw new Error("useAuthSession must be used inside an auth session provider");
  return session;
}

/** A stable token getter for the current user — used by useApi / useRoom. */
export function useToken(): TokenGetter {
  return useAuthSession().getToken;
}
