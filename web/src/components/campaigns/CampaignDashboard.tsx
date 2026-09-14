// The signed-in landing: the caller's campaigns + a create form. This is the
// front door — every play session is reached by picking a campaign here, then a
// session inside it, then the table.

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import type { Campaign, Me } from "@/lib/types";
import { useApi } from "@/lib/useApi";

import { Button, Card, ErrorText, Page, RoleBadge, SectionHeader, TextInput } from "../ui";

export default function CampaignDashboard({ me }: { me: Me }) {
  const api = useApi();
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!api) return;
    const client = api;
    let cancelled = false;
    (async () => {
      try {
        const list = await client.listCampaigns();
        if (!cancelled) setCampaigns(list);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "failed to load campaigns");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api]);

  async function createCampaign(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!api || !trimmed) return;
    setCreating(true);
    setError(null);
    try {
      const created = await api.createCampaign(trimmed);
      setName("");
      setCampaigns((prev) => (prev ? [...prev, created] : [created]));
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to create campaign");
    } finally {
      setCreating(false);
    }
  }

  return (
    <Page>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Your campaigns
        </h1>
        <p className="text-sm text-zinc-500">
          Signed in as {me.display_name || me.email}
        </p>
      </div>

      <ErrorText>{error}</ErrorText>

      <SectionHeader title="Campaigns" />
      {campaigns === null ? (
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : campaigns.length === 0 ? (
        <Card>
          <p className="text-sm text-zinc-500">
            No campaigns yet. Create one below to become its DM, then invite your
            players.
          </p>
        </Card>
      ) : (
        <ul className="space-y-2">
          {campaigns.map((c) => (
            <li key={c.id}>
              <Link
                href={`/campaigns/${c.id}`}
                className="flex items-center justify-between rounded-lg border border-zinc-200 bg-white px-4 py-3 transition-colors hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900/40 dark:hover:border-zinc-600"
              >
                <span className="font-medium text-zinc-900 dark:text-zinc-100">{c.name}</span>
                <RoleBadge role={c.my_role} />
              </Link>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-8">
        <SectionHeader title="Start a new campaign" />
        <form onSubmit={createCampaign} className="flex gap-2">
          <TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Campaign name"
            className="flex-1"
            aria-label="Campaign name"
          />
          <Button type="submit" disabled={creating || !name.trim()}>
            {creating ? "Creating…" : "Create"}
          </Button>
        </form>
      </div>
    </Page>
  );
}
