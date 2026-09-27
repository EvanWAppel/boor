"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, type ApiClient } from "@/lib/api";
import { isGuidedPayload, type GuidedCommand, type GuidedState } from "@/lib/guided";
import type { Character } from "@/lib/types";
import type { LogEntry } from "@/lib/useRoom";
import ConversationPanel from "./ConversationPanel";

const button = "rounded-lg border border-amber-700/60 bg-amber-950/50 px-4 py-3 text-left text-sm text-amber-100 hover:bg-amber-900/50 disabled:cursor-not-allowed disabled:opacity-40";

export default function GuidedPanel({ api, sessionId, campaignId, entries, characters, myId, isHost, connected, ended }: {
  api: ApiClient; sessionId: string; campaignId?: string; entries: LogEntry[]; characters: Character[];
  myId: string | null; isHost: boolean; connected: boolean; ended: boolean;
}) {
  const [snapshot, setSnapshot] = useState<GuidedState | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [reload, setReload] = useState(0);
  const [changing, setChanging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Keep the same command on ambiguous network failure: retry must never roll twice.
  const retry = useRef<GuidedCommand | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const latest = entries.findLast(e => e.kind === "narration" && !e.aiGenerated && isGuidedPayload(e.payload));
  const live = latest?.payload.state as GuidedState | undefined;
  const state = live && live.revision >= (snapshot?.revision ?? 0) ? live : snapshot;
  const me = myId ? state?.participants[myId] : null;
  const seat = myId ? state?.seats?.[myId] : null;
  const inLobby = state?.phase === "lobby";
  const allReady = Boolean(state && Object.keys(state.participants).length > 0 &&
    Object.values(state.seats ?? {}).every(s => s.ready));
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
      if (command.action === "select" || command.action === "watch") setChanging(false);
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
      <p className="text-xs uppercase tracking-widest text-amber-500">Learn by playing · {state && state.version < 3 ? "5" : "10"} minute introduction</p>
      <h2 className="mt-1 text-2xl font-semibold text-amber-100">{state?.conversation ? "A word with Mara" : "The river-road rescue"}</h2>
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
      {!inLobby && !state.conversation && <><p className="max-w-2xl text-sm leading-relaxed text-stone-300">{state.intro}</p>
      <p className="text-sm font-medium text-amber-200">Goal: get Mara and her cart onto firm ground.</p></>}
      {inLobby && <>
        <h3 className="font-medium text-stone-100">Get your party ready</h3>
        <p className="max-w-2xl text-sm text-stone-300">You play a character in a shared story. Choose what they try; the app explains when to roll and handles the rules. You can discuss choices in chat. No D&D experience needed.</p>
        <ul className="space-y-2 text-sm" aria-label="Lobby readiness">
          {Object.entries(state.seats ?? {}).sort(([a, sa], [b, sb]) => sa.player_name.localeCompare(sb.player_name) || a.localeCompare(b)).map(([id, s]) => <li key={id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-stone-800 p-3">
            <span><span className="font-medium text-stone-200">{s.player_name}{id === myId ? " (you)" : ""}</span><span className="text-stone-400"> · {s.watching ? "Watching" : state.participants[id]?.name ?? "Choosing a character"} · {s.ready ? "Ready" : "Not ready"}</span></span>
            {isHost && id !== myId && !ended && <button className="text-xs text-stone-400 underline disabled:opacity-40" disabled={disabled} onClick={() => act("exclude", { target_user_id: id })}>Mark {s.player_name} absent</button>}
          </li>)}
        </ul>
        {!ended && !seat && <button className={button} disabled={disabled} onClick={() => act("join")}>Join this lobby</button>}
        {!ended && seat && <div className="flex flex-wrap gap-2">
          {(me || seat.watching) && <button className={button} disabled={disabled} onClick={() => act(seat.ready ? "unready" : "ready")}>{seat.ready ? "Not ready yet" : "I’m ready"}</button>}
          {!seat.watching && <button className={button} disabled={disabled} onClick={() => act("watch")}>Watch this introduction</button>}
          {(me || seat.watching) && <button className={button} disabled={disabled} onClick={() => setChanging(!changing)}>{changing ? "Keep my choice" : seat.watching ? "Play a character instead" : "Change character"}</button>}
        </div>}
        {!ended && isHost && <div className="space-y-2">
          <button className={button} disabled={disabled || !allReady} onClick={() => act("begin")}>Begin adventure</button>
          <p className="text-xs text-stone-400">Everyone listed must be ready, with at least one playing character. Mark missing players absent; they can rejoin before you begin.</p>
        </div>}
        {!isHost && <p role="status" className="text-sm text-amber-200">The host will begin when everyone is ready.</p>}
      </>}
      {Object.keys(state.participants).length > 0 && <p className="text-xs text-stone-400">Rescue party: {Object.values(state.participants).map(p => p.name).join(", ")}{me ? ` · You are ${me.name}` : ""}</p>}
      {!ended && ((inLobby && seat && ((!me && !seat.watching) || changing)) || (state.version === 1 && state.phase === "ready" && !me)) && <>
        <h3 className="font-medium text-stone-100">1. Choose who you want to play</h3>
        <div className="flex flex-wrap gap-2">
          {characters.filter(c => c.player_id === myId).map(c => <button key={c.id} className={button} disabled={disabled} onClick={() => act("select", { character_id: c.id })}>Play as {c.name}</button>)}
          <button className={button} disabled={disabled} onClick={() => act("select", { pregen: "guardian" })}>Rowan · strong guardian<br /><span className="text-xs text-stone-400">Good at lifting and protecting</span></button>
          <button className={button} disabled={disabled} onClick={() => act("select", { pregen: "scholar" })}>Wren · curious scholar<br /><span className="text-xs text-stone-400">Good at noticing how things work</span></button>
        </div>
        <p className="text-xs text-stone-400">Starter characters are saved to your campaign. No character sheet to fill out.</p>
      </>}
      {!ended && state.version >= 2 && state.phase === "ready" && !me && <p role="status" className="text-sm text-amber-200">You’re watching this introduction. Follow the story and join the discussion in chat. Choose a character in the next session to play.</p>}
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
      {state.conversation && <ConversationPanel state={state} canPlay={Boolean(me)} isHost={isHost} disabled={disabled} ended={ended} act={act} />}
      {state.result && !state.conversation && <div className="space-y-2 rounded-lg border border-emerald-900 bg-emerald-950/20 p-4" role="status">
        <p className="font-mono text-lg text-emerald-200">{state.result.die} {state.result.bonus >= 0 ? "+" : "−"} {Math.abs(state.result.bonus)} = {state.result.total} · target {state.result.dc}</p>
        <p className="text-sm text-stone-200">{state.result.outcome}</p>
      </div>}
      {!ended && state.phase === "outcome" && (isHost
        ? <button className={button} disabled={disabled} onClick={() => act("continue")}>{state.version >= 3 ? "Talk with Mara" : "Finish the introduction"}</button>
        : <p className="text-sm text-amber-200">Your host will continue once everyone has read the outcome.</p>)}
      {state.phase === "complete" && <div className="space-y-2 text-sm text-stone-300">
        <h3 className="font-semibold text-amber-100">Introduction complete</h3>
        <p>You chose an approach, rolled a check{state.conversation ? ", spoke with Mara, and chose a destination" : ", and changed the story"}. That’s the basic rhythm of play.</p>
        <p>This introduction ends here. Start a new session from your campaign to try different choices or let another player lead.</p>
      </div>}
    </>}
    {(ended || state?.phase === "complete") && campaignId && <Link className={`${button} inline-block`} href={`/campaigns/${campaignId}`}>Back to campaign</Link>}
  </section>;
}
