"use client";

import CampaignDashboard from "@/components/campaigns/CampaignDashboard";
import { useMe } from "@/lib/useMe";

export default function Home() {
  const { me, status } = useMe();

  if (status === "signed-in" && me) {
    return <CampaignDashboard me={me} />;
  }

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-4xl font-semibold tracking-tight text-black dark:text-zinc-50">
        boor
      </h1>
      <p className="max-w-md text-lg leading-8 text-zinc-600 dark:text-zinc-400">
        An AI-assisted D&amp;D virtual tabletop where the campaign continues even
        when players are away.
      </p>
      {status === "loading" && <p className="text-sm text-zinc-500">Loading…</p>}
      {status === "signed-out" && (
        <p className="text-sm text-zinc-500">
          Sign in to see your campaigns and open a table.
        </p>
      )}
      {status === "unconfigured" && (
        <p className="max-w-md text-sm text-amber-600 dark:text-amber-400">
          The web app isn&apos;t configured yet. Set{" "}
          <code>NEXT_PUBLIC_API_BASE_URL</code> in <code>.env.local</code> to point
          at the service.
        </p>
      )}
      {status === "error" && (
        <p className="max-w-md text-sm text-rose-600 dark:text-rose-400">
          Couldn&apos;t reach the service. Make sure it&apos;s running, then reload.
        </p>
      )}
    </main>
  );
}
