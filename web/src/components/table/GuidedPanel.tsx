"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, type ApiClient } from "@/lib/api";
import type { GuidedCommand, GuidedState } from "@/lib/guided";
import type { Character } from "@/lib/types";
import type { LogEntry } from "@/lib/useRoom";

const button = "rounded-lg border border-amber-700/60 bg-amber-950/50 px-4 py-3 text-left text-sm text-amber-100 hover:bg-amber-900/50 disabled:cursor-not-allowed disabled:opacity-40";

export default function GuidedPanel({ api, sessionId, campaignId, entries, characters, myId, isHost, connected, ended }: {
  api: ApiClient; sessionId: string; campaignId?: string; entries: LogEntry[]; characters: Character[];
  myId: string | null; isHost: boolean; connected: boolean; ended: boolean;
}) {
  const [snapshot, setSnapshot] = useState<GuidedState | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Keep the same command on ambiguous network failure: retry must never roll twice.
  const retry = useRef<GuidedCommand | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const latest = entries.findLast(e => e.kind === "narration" && !e.aiGenerated && e.payload.type === "guided_cart_v1");
  const live = latest?.payload.state as GuidedState | undefined;
  const state = live && live.revision >= (snapshot?.revision ?? 0) ? live : snapshot;
  const me = myId ? state?.participants[myId] : null;
  const disabled = busy || !connected || ended || (!loaded && !state) || !myId || canRetry;

  useEffect(() => {
    let cancelled = false;
    api.getGuided(sessionId).then(r => {
      if (!cancelled) { setSnapshot(r.state); setLoaded(true); setError(null); }
    }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [api, sessionId, connected, reload]);

  async function submit(command: GuidedCommand) {
    if (busy) return;
    setBusy(true); setError(null); setCanRetry(false);
    retry.current = command;
    try {
      const result = await api.guidedCommand(sessionId, command);
      setSnapshot(result.state);
      retry.current = null;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send your action.");
      if (e instanceof ApiError && e.status < 500) {
        retry.current = null;
        try { setSnapshot((await api.getGuided(sessionId)).state); } catch { /* retry on reconnect */ }
      } else { setCanRetry(true); }
    } finally { setBusy(false); }
  }
  function act(action: GuidedCommand["action"], extra: Partial<GuidedCommand> = {}) {
    void submit({ request_id: crypto.randomUUID(), revision: state?.revision ?? 0, action, ...extra });
  }

  return <section className="max-h-[65dvh] shrink-0 space-y-4 overflow-y-auto border-b border-amber-900/50 bg-stone-950 p-5" aria-label="Guided adventure" aria-busy={busy}>
    <div>
      <p className="text-xs uppercase tracking-widest text-amber-500">Learn by playing · 5 minute introduction</p>
      <h2 className="mt-1 text-2xl font-semibold text-amber-100">The river-road rescue</h2>
    </div>
    {error && <div role="alert" className="text-sm text-rose-300">{error}
      {!loaded && !state && <button className={`${button} ml-3`} onClick={() => setReload(n => n + 1)}>Reload adventure</button>}
      {canRetry && <button className={`${button} ml-3`} disabled={busy || !connected || ended} onClick={() => retry.current && void submit(retry.current)}>Retry this action</button>}
    </div>}
    {!loaded && !state && <p className="text-sm text-stone-400">Loading the adventure…</p>}
    {ended && <p className="text-sm text-stone-300">This session has ended. Its story and results are saved below.</p>}
    {loaded && !state && <>
      <p className="max-w-2xl text-sm text-stone-300">Help a stranded driver rescue her cart. Pick a character, choose how to help, and let the app handle the dice and rules.</p>
      {isHost ? <button className={button} disabled={disabled} onClick={() => act("start")}>Start guided introduction</button>
        : <p className="text-sm text-amber-200">Your host can start the guided introduction here.</p>}
    </>}
    {state && <>
      <p className="max-w-2xl text-sm leading-relaxed text-stone-300">{state.intro}</p>
      <p className="text-sm font-medium text-amber-200">Goal: get Mara and her cart onto firm ground.</p>
      {Object.keys(state.participants).length > 0 && <p className="text-xs text-stone-400">Rescue party: {Object.values(state.participants).map(p => p.name).join(", ")}{me ? ` · You are ${me.name}` : ""}</p>}
      {!ended && state.phase === "ready" && !me && <>
        <h3 className="font-medium text-stone-100">1. Choose who you want to play</h3>
        <div className="flex flex-wrap gap-2">
          {characters.filter(c => c.player_id === myId).map(c => <button key={c.id} className={button} disabled={disabled} onClick={() => act("select", { character_id: c.id })}>Play as {c.name}</button>)}
          <button className={button} disabled={disabled} onClick={() => act("select", { pregen: "guardian" })}>Rowan · strong guardian<br /><span className="text-xs text-stone-400">Good at lifting and protecting</span></button>
          <button className={button} disabled={disabled} onClick={() => act("select", { pregen: "scholar" })}>Wren · curious scholar<br /><span className="text-xs text-stone-400">Good at noticing how things work</span></button>
        </div>
        <p className="text-xs text-stone-400">Starter characters are saved to your campaign. No character sheet to fill out.</p>
      </>}
      {!ended && state.phase === "ready" && me && <>
        <h3 className="font-medium text-stone-100">2. How will you help?</h3>
        <p className="text-sm text-stone-400">Discuss it in chat. Any player who has chosen a character can take the lead; the first choice starts the party’s check.</p>
        <div className="flex flex-wrap gap-2">
          <button className={button} disabled={disabled} onClick={() => act("approach", { approach: "lift" })}>Lift the wheel out of the mud<br /><span className="text-xs text-stone-400">Uses strength · Athletics</span></button>
          <button className={button} disabled={disabled} onClick={() => act("approach", { approach: "leverage" })}>Find a spot to use a branch as a lever<br /><span className="text-xs text-stone-400">Uses reasoning · Investigation</span></button>
        </div>
      </>}
      {state.phase === "check" && state.pending && <>
        <h3 className="font-medium text-stone-100">3. {state.pending.name} takes the lead</h3>
        <p className="text-sm text-stone-300">{state.pending.label}. A check answers whether an uncertain action works. Roll a twenty-sided die; your character adds {state.pending.bonus >= 0 ? "+" : ""}{state.pending.bonus}. A total of {state.pending.dc} or more succeeds.</p>
        <p className="text-xs text-stone-400">A lower roll changes what happens next. It won’t stop the adventure.</p>
        {!ended && (state.pending.user_id === myId
          ? <button className={button} disabled={disabled} onClick={() => act("roll")}>Roll for {state.pending.name}</button>
          : <p role="status" className="text-sm text-amber-200">Waiting for {state.pending.name}’s player to roll. You can cheer them on in chat.</p>)}
        {!ended && isHost && <button className="ml-3 text-xs text-stone-400 underline disabled:opacity-40" disabled={disabled} onClick={() => act("cancel")}>Release check so someone else can act</button>}
      </>}
      {state.result && <div className="space-y-2 rounded-lg border border-emerald-900 bg-emerald-950/20 p-4" role="status">
        <p className="font-mono text-lg text-emerald-200">{state.result.die} {state.result.bonus >= 0 ? "+" : "−"} {Math.abs(state.result.bonus)} = {state.result.total} · target {state.result.dc}</p>
        <p className="text-sm text-stone-200">{state.result.outcome}</p>
      </div>}
      {!ended && state.phase === "outcome" && (isHost
        ? <button className={button} disabled={disabled} onClick={() => act("continue")}>Finish the introduction</button>
        : <p className="text-sm text-amber-200">Your host will continue once everyone has read the outcome.</p>)}
      {state.phase === "complete" && <div className="space-y-2 text-sm text-stone-300">
        <h3 className="font-semibold text-amber-100">Introduction complete</h3>
        <p>You chose an approach, rolled a check, and changed the story. That’s the basic rhythm of play.</p>
        <p>This first introduction ends here. Start a new session from your campaign to try the other approach or let another player lead.</p>
      </div>}
    </>}
    {(ended || state?.phase === "complete") && campaignId && <Link className={`${button} inline-block`} href={`/campaigns/${campaignId}`}>Back to campaign</Link>}
  </section>;
}
