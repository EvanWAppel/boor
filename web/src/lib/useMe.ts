// Resolve the signed-in account for gating screens.
//
// Waits for the auth provider to load before deciding anything, so a signed-in
// user never flashes the signed-out pitch while Clerk boots. Distinguishes
// "signed out" (a 401/403 or no session) from a genuine service error so the UI
// can prompt sign-in vs. surface a failure.
//
// The statuses knowable at render (unconfigured / still-loading / signed-out) are
// derived, not stored — only the async /me fetch touches state, and only after an
// await, so it never sets state synchronously inside the effect.

"use client";

import { useEffect, useState } from "react";

import { ApiError } from "./api";
import { useAuthSession } from "./auth";
import type { Me } from "./types";
import { useApi } from "./useApi";

export type MeStatus =
  | "loading"
  | "signed-in"
  | "signed-out"
  | "unconfigured"
  | "error";

export interface MeState {
  me: Me | null;
  status: MeStatus;
  error: string | null;
}

export function useMe(): MeState {
  const api = useApi();
  const { isLoaded, isSignedIn } = useAuthSession();

  // Everything we can decide without a request. `null` means "signed in and
  // ready — go fetch /me".
  const baseStatus: MeStatus | null = !api
    ? "unconfigured"
    : !isLoaded
      ? "loading"
      : !isSignedIn
        ? "signed-out"
        : null;

  const [fetched, setFetched] = useState<MeState>({
    me: null,
    status: "loading",
    error: null,
  });

  useEffect(() => {
    if (baseStatus !== null || !api) return; // not signed in / not ready yet
    const client = api;
    let cancelled = false;
    (async () => {
      try {
        const resolved = await client.me();
        if (!cancelled) setFetched({ me: resolved, status: "signed-in", error: null });
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
          setFetched({ me: null, status: "signed-out", error: null });
        } else {
          setFetched({
            me: null,
            status: "error",
            error: e instanceof Error ? e.message : "failed to load",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, baseStatus]);

  if (baseStatus !== null) return { me: null, status: baseStatus, error: null };
  return fetched;
}
