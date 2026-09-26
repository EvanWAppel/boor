// A memoized service client bound to the current token + configured base URL.
// One hook so every screen shares the same wiring (and the same auth seam).

"use client";

import { useMemo } from "react";

import { createApiClient, type ApiClient } from "./api";
import { useToken } from "./auth";

/** The service base URL, from the build-time public env (see .env.local.example). */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

/** A typed service client for the signed-in caller, or `null` if unconfigured. */
export function useApi(): ApiClient | null {
  const getToken = useToken();
  return useMemo(() => {
    if (!API_BASE_URL) return null;
    return createApiClient({ baseUrl: API_BASE_URL, getToken });
  }, [getToken]);
}
