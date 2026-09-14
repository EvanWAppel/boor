// Auth seam for the web app — the single place the token comes from.
//
// The whole app takes its bearer token through `useToken()`, which returns a stable
// `getToken` for `createApiClient` / `connectSessionRoom`. Which implementation is
// used is decided once, at build time, by whether a Clerk publishable key is present:
//
//   • key present (Railway, local web/.env.local) → Clerk's `useAuth().getToken`,
//     returning the customized session token that carries the `email`/`name` claims
//     the service requires (see CLERK-SETUP.md Step 2).
//   • key absent (CI's `pnpm build`, or before Clerk is wired locally) → a dev token
//     from localStorage/env, so pages compile and CI stays green without a key.
//
// `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` is inlined at build time, so `CLERK_ENABLED` is
// a constant within any given build. Picking the hook once at module load (rather
// than branching inside a component) keeps the rules of hooks satisfied.

"use client";

import { useCallback } from "react";

import { useAuth } from "@clerk/nextjs";

import type { TokenGetter } from "./api";

/** localStorage key a developer can set to a minted token for local testing. */
export const DEV_TOKEN_KEY = "boor_dev_token";

/** True when Clerk is configured; a build-time constant (public key is inlined). */
const CLERK_ENABLED = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

/** Read the current dev token, if any (localStorage takes precedence over env). */
export function readDevToken(): string | null {
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem(DEV_TOKEN_KEY);
    if (stored) return stored;
  }
  return process.env.NEXT_PUBLIC_DEV_TOKEN ?? null;
}

/** Auth readiness + identity, provider-agnostic (Clerk when keyed, else dev token). */
export interface AuthSession {
  /** Stable getter for the bearer token (null when signed out / no dev token). */
  getToken: TokenGetter;
  /** False until the auth provider has resolved the current session. */
  isLoaded: boolean;
  /** Whether there is a signed-in user (or a dev token, in the keyless path). */
  isSignedIn: boolean;
}

/** Clerk-backed session — the real path once a publishable key is set. */
function useClerkSession(): AuthSession {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  return { getToken, isLoaded, isSignedIn: Boolean(isSignedIn) };
}

/** Dev-token session — used in CI/builds and before Clerk is wired locally. */
function useDevSession(): AuthSession {
  const getToken = useCallback(() => readDevToken(), []);
  // Dev token is resolved once at load; readiness is immediate.
  return { getToken, isLoaded: true, isSignedIn: Boolean(readDevToken()) };
}

/** The current auth session (Clerk when configured, else the dev-token seam). */
export const useAuthSession: () => AuthSession = CLERK_ENABLED
  ? useClerkSession
  : useDevSession;

/** A stable token getter for the current user — used by useApi / useRoom. */
export function useToken(): TokenGetter {
  return useAuthSession().getToken;
}
