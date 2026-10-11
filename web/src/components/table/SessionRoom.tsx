// The theater-of-the-mind table (MILE-1). Composes the shared log, composer,
// dice, initiative, presence, and read-only sheets over one realtime room.
//
// All data flows through the injected api client + the useRoom hook, so this is
// Clerk-agnostic: give it a token (dev token today, Clerk tomorrow) and it lights
// up against a running service. No map or tokens by design (D-04).

"use client";

import { useEffect, useState } from "react";

import type { Character, GameSession, MembershipRole, Recap } from "@/lib/types";
import { recapsToReadFirst } from "@/lib/recaps";
import { useApi } from "@/lib/useApi";
import { useRoom } from "@/lib/useRoom";
import { useAuthSession } from "@/lib/auth";
import { WS_FORBIDDEN, WS_NOT_FOUND, WS_UNAUTHORIZED } from "@/lib/ws";

import { isGuidedPayload } from "@/lib/guided";

import Composer from "./Composer";
import GuidedPanel from "./GuidedPanel";
import DiceRoller from "./DiceRoller";
import InitiativeTracker from "./InitiativeTracker";
import Log from "./Log";
import Presence from "./Presence";
import SheetPanel from "./SheetPanel";
import StandInPanel from "./StandInPanel";
import RecapCard from "../recaps/RecapCard";

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-stone-800 bg-stone-900/60">
      <h2 className="border-b border-stone-800 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-stone-400">
        {title}
      </h2>
      <div className="p-3">{children}</div>
    </section>
  );
}

function statusLabel(status: string, closeCode: number | null): string {
  if (status === "open") return "Connected";
  if (status === "reconnecting") return "Reconnecting…";
  if (status === "connecting") return "Connecting…";
  if (closeCode === WS_UNAUTHORIZED) return "Not signed in";
  if (closeCode === WS_FORBIDDEN) return "Not a member of this campaign";
  if (closeCode === WS_NOT_FOUND) return "Session not found";
  return "Disconnected";
}

export default function SessionRoom({ sessionId }: { sessionId: string }) {
  const auth = useAuthSession();
  if (!auth.isLoaded) return <p className="p-6">Loading your session…</p>;
  if (!auth.isSignedIn) return <p className="p-6">Sign in to enter this table.</p>;
  return <SessionRoomContent key={`${sessionId}:${auth.userId}`} sessionId={sessionId} />;
}

function SessionRoomContent({ sessionId }: { sessionId: string }) {
  const api = useApi();
  const room = useRoom(sessionId, api);

  const [session, setSession] = useState<GameSession | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [myId, setMyId] = useState<string | null>(null);
  const [myRole, setMyRole] = useState<MembershipRole | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  // AI-09: my unread recaps are shown before the table ("while you were away").
  const [recaps, setRecaps] = useState<Recap[]>([]);
  const [recapsDone, setRecapsDone] = useState(false);

  useEffect(() => {
    if (!api) return;
    let cancelled = false;
    (async () => {
      try {
        const s = await api.getSession(sessionId);
        if (cancelled) return;
        setSession(s);
        const [me, members, chars] = await Promise.all([
          api.me(),
          api.listMembers(s.campaign_id),
          api.listCharacters(s.campaign_id),
        ]);
        if (cancelled) return;
        // A recap failure must not keep anyone from the table; it's logged and skipped.
        // Bounded: a slow recap request must never hold anyone at "Loading…".
        Promise.race([
          api.listRecaps(s.campaign_id),
          new Promise<never>((_, reject) => setTimeout(() => reject(new Error("recaps timed out")), 8000)),
        ])
          .then(r => { if (!cancelled) setRecaps(recapsToReadFirst(r)); })
          .catch(e => console.error("[boor] could not load recaps", e))
          .finally(() => { if (!cancelled) setRecapsDone(true); });
        setCharacters(chars);
        setMyId(me.id);
        setMyRole(members.find((m) => m.user_id === me.id)?.role ?? null);
      } catch (e) {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "failed to load");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, sessionId]);

  const guidedRevision = room.entries.findLast(e => e.kind === "narration" && isGuidedPayload(e.payload))?.seq;
  useEffect(() => {
    if (!api || !session || !guidedRevision) return;
    let cancelled = false;
    api.listCharacters(session.campaign_id).then(chars => {
      if (!cancelled) setCharacters(chars);
    }).catch(() => { /* existing sheets remain available until reconnect */ });
    return () => { cancelled = true; };
  }, [api, session, guidedRevision]);

  if (!api) {
    return (
      <div className="m-auto max-w-md p-8 text-center text-sm text-stone-400">
        The web app isn&apos;t configured yet. Set{" "}
        <code className="text-amber-300">NEXT_PUBLIC_API_BASE_URL</code> in{" "}
        <code>.env.local</code> to point at the service.
      </div>
    );
  }

  const isDm = myRole === "dm";

  // Hold the table until the recap check finishes (no flash of the table first). A
  // failed check still sets recapsDone, so it never locks anyone out.
  if (!recapsDone && !loadError) return <p className="p-6 text-sm text-stone-400">Loading your session…</p>;

  if (recapsDone && recaps.length > 0) {
    return <div className="mx-auto w-full max-w-2xl space-y-4 p-6">
      <h1 className="text-xl font-semibold text-amber-100">Before you sit down: while you were away…</h1>
      <p className="text-sm text-stone-400">Your character was played by their AI stand-in last time. Here’s what they did, in their own words.</p>
      {recaps.map(r => <RecapCard key={r.id} api={api} recap={r} isDm={isDm} theme="table"
        onChange={updated => setRecaps(prev => prev.map(x => (x.id === updated.id ? updated : x)))} />)}
      <button className="rounded-lg border border-amber-700/60 bg-amber-950/50 px-4 py-3 text-sm text-amber-100 hover:bg-amber-900/50"
        onClick={() => {
          void Promise.allSettled(recaps.filter(r => !r.read).map(r => api.markRecapRead(r.id)))
            .then(results => results.forEach(x => { if (x.status === "rejected") console.error("[boor] could not mark recap read", x.reason); }));
          setRecaps([]);
        }}>I’ve read it. Continue to the table</button>
    </div>;
  }
  const connected = room.status === "open";
  const ended = session?.status === "ended" || room.entries.some(e => e.kind === "system" && e.payload.type === "session_ended");
  const writable = connected && !ended;

  // Desktop: a two-column reading layout capped at a comfortable width — what you
  // act on (scene + tools) on the left, the running story log on the right, each
  // scrolling on its own (see `[data-table-app]` in globals.css). Narrow windows
  // stack scene → log → tools.
  return (
    <div data-table-app className="mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-stone-800 px-4 py-3">
        <div>
          <h1 className="text-lg font-semibold text-amber-100">
            {session?.title ?? "The table"}
          </h1>
          <p className="text-xs text-stone-500">
            {session ? `${ended ? "ended" : session.status} · ` : ""}
            {room.present.length} present
          </p>
        </div>
        <span
          className={`rounded px-2 py-1 text-xs ${
            connected
              ? "bg-emerald-900/60 text-emerald-200"
              : "bg-stone-800 text-stone-400"
          }`}
        >
          {statusLabel(room.status, room.closeCode)}
        </span>
      </header>

      {loadError && (
        <p className="border-b border-rose-900/50 bg-rose-950/40 px-4 py-2 text-xs text-rose-300">
          {loadError}
        </p>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,28rem)] lg:grid-rows-[minmax(0,1fr)]">
        {/* What you act on: the scene, then the table tools. One scroll column on
            desktop; on narrow windows `contents` lets the log slot in between. */}
        <div className="contents lg:block lg:min-h-0 lg:overflow-y-auto">
          <div className="order-1">
            <GuidedPanel api={api} sessionId={sessionId} campaignId={session?.campaign_id} entries={room.entries} characters={characters}
              myId={myId} isHost={isDm} connected={connected} ended={ended} />
          </div>

          {/* Table tools, under the scene on desktop. */}
          <aside className="order-3 space-y-3 p-3">
          {!guidedRevision && <><Panel title="Dice">
            <DiceRoller api={api} onRoll={room.sendRoll} disabled={!writable} />
          </Panel>
          <Panel title="Initiative">
            <InitiativeTracker
              initiative={room.initiative}
              canEdit={isDm && writable}
              onChange={room.setInitiative}
            />
          </Panel>
          </>}
          <Panel title="At the table">
            <Presence present={room.present} />
          </Panel>
          {!guidedRevision && <Panel title="AI stand-ins">
            <StandInPanel api={api} sessionId={sessionId} characters={characters}
              myId={myId} isDm={isDm} connected={writable && session?.status === "active"}
              entries={room.entries} thinking={room.thinking} />
          </Panel>}
          <Panel title="Party">
            <SheetPanel characters={characters} />
          </Panel>
          </aside>
        </div>

        {/* The running story: log + composer, pinned to the right on desktop. */}
        <section aria-label="Story log" className="order-2 flex min-h-0 flex-col border-stone-800 lg:border-l">
          <h2 className="border-b border-stone-800 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-stone-400">
            Story so far
          </h2>
          <Log entries={room.entries} />
          <Composer
            onChat={room.sendChat}
            onOoc={room.sendOoc}
            disabled={!writable}
          />
        </section>
      </div>
    </div>
  );
}
