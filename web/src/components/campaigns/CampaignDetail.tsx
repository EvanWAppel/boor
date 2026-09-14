// A campaign's hub: the sessions you can join (DM opens/closes them), the roster
// (DM invites players), and the party's characters. Every play session at the
// table is reached from here — pick a session and enter.

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import type {
  Campaign,
  Character,
  CharacterCreate,
  GameSession,
  Member,
  MembershipRole,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";

import {
  Button,
  Card,
  ErrorText,
  Page,
  RoleBadge,
  SectionHeader,
  StatusBadge,
  TextInput,
} from "../ui";
import NewCharacterForm from "./NewCharacterForm";

export default function CampaignDetail({ campaignId }: { campaignId: string }) {
  const api = useApi();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [sessions, setSessions] = useState<GameSession[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [myId, setMyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [notMember, setNotMember] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!api) return;
    const client = api;
    let cancelled = false;
    (async () => {
      try {
        const [campaigns, me] = await Promise.all([client.listCampaigns(), client.me()]);
        if (cancelled) return;
        setError(null);
        setMyId(me.id);
        const found = campaigns.find((c) => c.id === campaignId) ?? null;
        setCampaign(found);
        if (!found) {
          setNotMember(true);
          return; // the finally still clears loading
        }
        const [s, m, ch] = await Promise.all([
          client.listSessions(campaignId),
          client.listMembers(campaignId),
          client.listCharacters(campaignId),
        ]);
        if (cancelled) return;
        setSessions(s);
        setMembers(m);
        setCharacters(ch);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "failed to load campaign");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, campaignId]);

  const isDm = campaign?.my_role === "dm";

  async function startSession() {
    if (!api) return;
    setError(null);
    try {
      const created = await api.createSession(campaignId);
      setSessions((prev) => [created, ...prev]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to start session");
    }
  }

  async function endSession(id: string) {
    if (!api) return;
    setError(null);
    try {
      const ended = await api.endSession(id);
      setSessions((prev) => prev.map((s) => (s.id === id ? ended : s)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to end session");
    }
  }

  async function addCharacter(character: CharacterCreate) {
    if (!api) return;
    const created = await api.createCharacter(campaignId, character);
    setCharacters((prev) => [...prev, created]);
  }

  if (loading) {
    return (
      <Page>
        <p className="text-sm text-zinc-500">Loading campaign…</p>
      </Page>
    );
  }

  if (notMember) {
    return (
      <Page>
        <Card>
          <p className="text-sm text-zinc-600 dark:text-zinc-300">
            This campaign doesn&apos;t exist, or you&apos;re not a member of it.
          </p>
          <Link
            href="/"
            className="mt-2 inline-block text-sm text-zinc-500 underline hover:text-zinc-800 dark:hover:text-zinc-200"
          >
            ← Back to your campaigns
          </Link>
        </Card>
      </Page>
    );
  }

  return (
    <Page>
      <div className="mb-6">
        <Link
          href="/"
          className="text-sm text-zinc-500 underline hover:text-zinc-800 dark:hover:text-zinc-200"
        >
          ← Campaigns
        </Link>
        <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          {campaign?.name}
          {campaign && <RoleBadge role={campaign.my_role} />}
        </h1>
      </div>

      <ErrorText>{error}</ErrorText>

      {/* Sessions */}
      <section className="mb-8">
        <SectionHeader
          title="Sessions"
          action={isDm ? <Button onClick={startSession}>Start a session</Button> : undefined}
        />
        {sessions.length === 0 ? (
          <Card>
            <p className="text-sm text-zinc-500">
              {isDm
                ? "No sessions yet. Start one to open the table."
                : "No sessions yet. Your DM will open one."}
            </p>
          </Card>
        ) : (
          <ul className="space-y-2">
            {sessions.map((s) => (
              <li
                key={s.id}
                className="flex items-center justify-between rounded-lg border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/40"
              >
                <div className="flex items-center gap-2">
                  <StatusBadge status={s.status} />
                  <span className="text-zinc-900 dark:text-zinc-100">
                    {s.title || "Untitled session"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {isDm && s.status !== "ended" && (
                    <Button variant="danger" onClick={() => endSession(s.id)}>
                      End
                    </Button>
                  )}
                  <Link
                    href={`/table/${s.id}`}
                    className="inline-flex items-center rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
                  >
                    {s.status === "ended" ? "View log" : "Enter table"}
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Players / roster */}
      <section className="mb-8">
        <SectionHeader title="Players" />
        <ul className="mb-3 space-y-1">
          {members.map((m) => (
            <li
              key={m.user_id}
              className="flex items-center justify-between rounded-md px-1 py-1 text-sm"
            >
              <span className="text-zinc-800 dark:text-zinc-200">
                {m.display_name || m.user_id.slice(0, 8)}
                {m.user_id === myId && (
                  <span className="ml-1 text-xs text-zinc-400">(you)</span>
                )}
              </span>
              <RoleBadge role={m.role} />
            </li>
          ))}
        </ul>
        {isDm && <InviteForm campaignId={campaignId} />}
      </section>

      {/* Characters */}
      <section>
        <SectionHeader title="Characters" />
        {characters.length > 0 && (
          <ul className="mb-3 space-y-1">
            {characters.map((ch) => (
              <li
                key={ch.id}
                className="flex items-center justify-between rounded-md px-1 py-1 text-sm"
              >
                <span className="text-zinc-800 dark:text-zinc-200">
                  {ch.name}{" "}
                  <span className="text-xs text-zinc-400">level {ch.level}</span>
                </span>
                <span className="text-xs text-zinc-400">
                  {ch.player_id === null
                    ? "NPC / pregen"
                    : ch.player_id === myId
                      ? "yours"
                      : "another player"}
                </span>
              </li>
            ))}
          </ul>
        )}
        <NewCharacterForm onCreate={addCharacter} />
      </section>
    </Page>
  );
}

/** DM-only: mint an invite and show the shareable link. */
function InviteForm({ campaignId }: { campaignId: string }) {
  const api = useApi();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<MembershipRole>("player");
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = email.trim();
    if (!api || !trimmed) return;
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      const created = await api.createInvite(campaignId, trimmed, role);
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      setLink(`${origin}/invite/${created.token}`);
      setEmail("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to create invite");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      // Clipboard may be unavailable (insecure context); the link is still shown.
    }
  }

  return (
    <Card>
      <form onSubmit={invite} className="flex flex-wrap items-center gap-2">
        <TextInput
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="player@example.com"
          className="flex-1"
          aria-label="Invite email"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as MembershipRole)}
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          aria-label="Invite role"
        >
          <option value="player">Player</option>
          <option value="dm">DM</option>
        </select>
        <Button type="submit" disabled={busy || !email.trim()}>
          {busy ? "Inviting…" : "Create invite"}
        </Button>
      </form>
      <ErrorText>{error}</ErrorText>
      {link && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <code className="flex-1 break-all rounded bg-zinc-100 px-2 py-1 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
            {link}
          </code>
          <Button type="button" variant="secondary" onClick={copy}>
            {copied ? "Copied!" : "Copy link"}
          </Button>
        </div>
      )}
      {link && (
        <p className="mt-2 text-xs text-zinc-400">
          Send this link to your player. They&apos;ll sign in and join the campaign.
        </p>
      )}
    </Card>
  );
}
