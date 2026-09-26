// Redeem an invite link: /invite/<token>. Accepting requires a signed-in account
// (the service ties the membership to the caller), so if the visitor is signed
// out we prompt them to sign in first, then accept automatically once they are.

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { AcceptResult } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useMe } from "@/lib/useMe";

import { Button, Card, ErrorText, Page } from "../ui";

export default function AcceptInvite({ token }: { token: string }) {
  const api = useApi();
  const { status } = useMe();
  const router = useRouter();
  const [result, setResult] = useState<AcceptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const attempted = useRef(false);

  useEffect(() => {
    if (!api || status !== "signed-in" || attempted.current) return;
    attempted.current = true;
    (async () => {
      try {
        const accepted = await api.acceptInvite(token);
        setResult(accepted);
        // Land the player straight in the campaign they just joined.
        router.push(`/campaigns/${accepted.campaign_id}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to accept invite");
      }
    })();
  }, [api, status, token, router]);

  return (
    <Page>
      <Card>
        <h1 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Campaign invitation
        </h1>

        {status === "unconfigured" && (
          <p className="mt-2 text-sm text-amber-600 dark:text-amber-400">
            The web app isn&apos;t configured yet. Set <code>NEXT_PUBLIC_API_BASE_URL</code>.
          </p>
        )}

        {status === "loading" && (
          <p className="mt-2 text-sm text-zinc-500">Checking your session…</p>
        )}

        {status === "signed-out" && (
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
            Sign in (top right) to accept this invitation. It&apos;ll be applied
            automatically once you do.
          </p>
        )}

        {status === "signed-in" && !result && !error && (
          <p className="mt-2 text-sm text-zinc-500">Joining the campaign…</p>
        )}

        {result && (
          <div className="mt-2">
            <p className="text-sm text-emerald-700 dark:text-emerald-400">
              You&apos;ve joined the campaign as {result.role === "dm" ? "a DM" : "a player"}.
            </p>
            <Link href={`/campaigns/${result.campaign_id}`} className="mt-3 inline-block">
              <Button>Go to campaign</Button>
            </Link>
          </div>
        )}

        {error && (
          <div className="mt-2">
            <ErrorText>{error}</ErrorText>
            <Link
              href="/"
              className="mt-2 inline-block text-sm text-zinc-500 underline hover:text-zinc-800 dark:hover:text-zinc-200"
            >
              ← Back to your campaigns
            </Link>
          </div>
        )}
      </Card>
    </Page>
  );
}
