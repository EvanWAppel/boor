"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, type ApiClient } from "@/lib/api";
import { CHECK_SCENES, isGuidedPayload, pauseControls, type GuidedCommand, type GuidedState } from "@/lib/guided";
import { lobbyStatus } from "@/lib/lobby";
import type { Character } from "@/lib/types";
import type { LogEntry } from "@/lib/useRoom";
import ConversationPanel from "./ConversationPanel";
import CombatPanel from "./CombatPanel";

const button = "rounded-lg border border-amber-700/60 bg-amber-950/50 px-4 py-3 text-left text-sm text-amber-100 hover:bg-amber-900/50 disabled:cursor-not-allowed disabled:opacity-40";
const textarea = "w-full max-w-2xl rounded-lg border border-stone-700 bg-stone-900/60 p-2 text-sm text-stone-100 placeholder:text-stone-500 disabled:opacity-40";

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
  const [proposalText, setProposalText] = useState("");
  const [declineText, setDeclineText] = useState("");
  const [noteText, setNoteText] = useState("");
  const latest = entries.findLast(e => e.kind === "narration" && !e.aiGenerated && isGuidedPayload(e.payload));
  const live = latest?.payload.state as GuidedState | undefined;
  const state = live && live.revision >= (snapshot?.revision ?? 0) ? live : snapshot;
  const me = myId ? state?.participants[myId] : null;
  const seat = myId ? state?.seats?.[myId] : null;
  const inLobby = state?.phase === "lobby";
  const v5 = (state?.version ?? 0) >= 5;
  const scene = state?.scene ?? null;
  const inCheckScene = v5 && !!scene && CHECK_SCENES.has(scene);
  const lobby = state ? lobbyStatus(state, myId, isHost) : null;
  const controlsDisabled = busy || !connected || ended || (!loaded && !state) || !myId || canRetry;
  // A pause freezes game actions only; the pause controls themselves stay usable.
  const disabled = controlsDisabled || !!state?.paused;
  const pause = state ? pauseControls(state, myId, isHost) : null;

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
      <p className="text-xs uppercase tracking-widest text-amber-500">Learn by playing · {state && state.version >= 5 ? "20" : state && state.version < 3 ? "5" : state?.version === 3 ? "10" : "15"} minute introduction</p>
      <h2 className="mt-1 text-2xl font-semibold text-amber-100">{state && state.version >= 5 ? (state.scene_title ?? "The river-road rescue") : state?.encounter ? "Practice with Mara" : state?.conversation ? "A word with Mara" : "The river-road rescue"}</h2>
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
      {!ended && state.paused && <div role="status" className="space-y-2 rounded-lg border border-sky-800/60 bg-sky-950/30 p-4">
        <p className="text-sm font-medium text-sky-100">{state.paused.user_id === myId ? "You paused play." : `${state.paused.name} paused play.`} Game actions wait until play resumes; chat stays open.</p>
        {state.paused.note && <p className="text-sm italic text-stone-200">“{state.paused.note}”</p>}
        {pause?.canNote && <div className="space-y-2">
          <label htmlFor="guided-pause-note" className="block text-xs text-stone-400">Optional: add a note for the table.</label>
          <textarea id="guided-pause-note" className={textarea} rows={2} maxLength={500} value={noteText} disabled={controlsDisabled} onChange={e => setNoteText(e.target.value)} />
          <button className={button} disabled={controlsDisabled || !noteText.trim()} onClick={() => { act("pause_note", { text: noteText.trim() }); setNoteText(""); }}>Share note</button>
        </div>}
        {pause?.canResume
          ? <button className={button} disabled={controlsDisabled} onClick={() => act("resume")}>Resume play</button>
          : <p className="text-xs text-stone-400">{state.paused.name} or the host can resume.</p>}
      </div>}
      {!ended && pause?.canPause && <button className="text-xs text-stone-400 underline disabled:opacity-40" disabled={controlsDisabled} onClick={() => act("pause")}>Pause play</button>}
      {!inLobby && v5 && scene && state.phase !== "complete" && <><p className="max-w-2xl text-sm leading-relaxed text-stone-300">{state.scene_intro}</p>
      {state.goal && <p className="text-sm font-medium text-amber-200">Goal: {state.goal}</p>}</>}
      {!inLobby && !v5 && !state.conversation && <><p className="max-w-2xl text-sm leading-relaxed text-stone-300">{state.intro}</p>
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
          {!seat.watching && <button className={button} disabled={disabled} onClick={() => act("watch")}>Join as spectator</button>}
          {(me || seat.watching) && <button className={button} disabled={disabled} onClick={() => setChanging(!changing)}>{changing ? "Keep my choice" : seat.watching ? "Play a character instead" : "Change character"}</button>}
        </div>}
        {!ended && seat?.watching && <p className="text-sm text-stone-300">You’re watching as a spectator. You can follow the story and chat once the host begins. To take actions, choose “Play a character instead”.</p>}
        {!ended && <p role="status" className="text-sm text-amber-200">{lobby?.message}</p>}
        {!ended && isHost && <div className="space-y-2">
          <button className={button} disabled={disabled || !lobby?.canBegin} onClick={() => act("begin")}>Begin adventure</button>
          <p className="text-xs text-stone-400">The host can play or watch. Mark missing players absent; they can rejoin before you begin.</p>
        </div>}
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
      {!ended && state.phase === "ready" && me && !state.proposal && <>
        <h3 className="font-medium text-stone-100">How will you help?</h3>
        <p className="text-sm text-stone-400">Discuss it in chat. Any player who has chosen a character can take the lead; the first choice starts the party’s check.</p>
        <div className="flex flex-wrap gap-2">
          {v5
            ? (state.actions ?? []).map(a => <button key={a.id} className={button} disabled={disabled} onClick={() => act("approach", { approach: a.id })}>{a.label}<br /><span className="text-xs text-stone-400">{a.hint}</span></button>)
            : <>
              <button className={button} disabled={disabled} onClick={() => act("approach", { approach: "lift" })}>Lift the wheel out of the mud<br /><span className="text-xs text-stone-400">Uses strength · Athletics</span></button>
              <button className={button} disabled={disabled} onClick={() => act("approach", { approach: "leverage" })}>Find a spot to use a branch as a lever<br /><span className="text-xs text-stone-400">Uses reasoning · Investigation</span></button>
            </>}
        </div>
        {v5 && <div className="space-y-2">
          <label htmlFor="guided-proposal" className="block text-xs text-stone-400">Something else in mind? Describe it and the host will decide how to handle it.</label>
          <textarea id="guided-proposal" className={textarea} rows={2} maxLength={500} value={proposalText} disabled={disabled} placeholder="e.g. I look for a plank to wedge under the wheel" onChange={e => setProposalText(e.target.value)} />
          <button className={button} disabled={disabled || !proposalText.trim()} onClick={() => { act("propose", { text: proposalText.trim() }); setProposalText(""); }}>Try something else</button>
        </div>}
      </>}
      {v5 && state.phase === "ready" && state.proposal && <div className="space-y-2 rounded-lg border border-amber-800/60 bg-amber-950/20 p-4">
        <p className="text-sm text-amber-200">{state.proposal.name} wants to try something else:</p>
        <p className="text-sm italic text-stone-200">“{state.proposal.text}”</p>
        {!ended && isHost
          ? <div className="space-y-2">
              <p className="text-xs text-stone-400">Run it as one of the offered actions, or reply with a reason if it isn’t possible here.</p>
              <div className="flex flex-wrap gap-2">
                {(state.actions ?? []).map(a => <button key={a.id} className={button} disabled={disabled} onClick={() => act("accept_proposal", { approach: a.id })}>Run as {a.label}<br /><span className="text-xs text-stone-400">{a.hint}</span></button>)}
              </div>
              <textarea className={textarea} rows={2} maxLength={500} value={declineText} disabled={disabled} placeholder="Reply if this isn’t possible here" onChange={e => setDeclineText(e.target.value)} />
              <button className={button} disabled={disabled || !declineText.trim()} onClick={() => { act("decline_proposal", { text: declineText.trim() }); setDeclineText(""); }}>Send reply instead</button>
            </div>
          : <p role="status" className="text-sm text-amber-200">{state.proposal.user_id === myId ? "Your idea is with the host." : "Waiting for the host to respond to the proposal."}</p>}
      </div>}
      {state.phase === "check" && state.pending && <>
        <h3 className="font-medium text-stone-100">{v5 ? "" : "3. "}{state.pending.name} takes the lead</h3>
        <p className="text-sm text-stone-300">{state.pending.label}. A check answers whether an uncertain action works. Roll a twenty-sided die; your character adds {state.pending.bonus >= 0 ? "+" : ""}{state.pending.bonus}. A total of {state.pending.dc} or more succeeds.</p>
        <p className="text-xs text-stone-400">A lower roll changes what happens next. It won’t stop the adventure.</p>
        {!ended && (state.pending.user_id === myId
          ? <button className={button} disabled={disabled} onClick={() => act("roll")}>Roll for {state.pending.name}</button>
          : <p role="status" className="text-sm text-amber-200">Waiting for {state.pending.name}’s player to roll. You can cheer them on in chat.</p>)}
        {!ended && isHost && <button className="ml-3 text-xs text-stone-400 underline disabled:opacity-40" disabled={disabled} onClick={() => act("cancel")}>Release check so someone else can act</button>}
      </>}
      {state.conversation && (v5 ? scene === "mara" : !state.encounter) && <ConversationPanel state={state} canPlay={Boolean(me)} isHost={isHost} disabled={disabled} ended={ended} act={act} />}
      {state.encounter && (v5 ? scene === "battle" : true) && <CombatPanel state={state} myId={myId} isHost={isHost} disabled={disabled} ended={ended} act={act} />}
      {state.result && (v5 ? inCheckScene : !state.conversation) && <div className="space-y-2 rounded-lg border border-emerald-900 bg-emerald-950/20 p-4" role="status">
        <p className="font-mono text-lg text-emerald-200">{state.result.die} {state.result.bonus >= 0 ? "+" : "−"} {Math.abs(state.result.bonus)} = {state.result.total} · target {state.result.dc}</p>
        <p className="text-sm text-stone-200">{state.result.outcome}</p>
      </div>}
      {!ended && state.phase === "outcome" && (isHost
        ? <button className={button} disabled={disabled} onClick={() => act("continue")}>{v5 ? "Continue" : state.version >= 3 ? "Talk with Mara" : "Finish the introduction"}</button>
        : <p className="text-sm text-amber-200">Your host will continue once everyone has read the outcome.</p>)}
      {v5 && scene === "recap" && state.recap && <div className="space-y-2 rounded-lg border border-amber-900/60 bg-amber-950/20 p-4">
        <h3 className="font-semibold text-amber-100">What you did</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm text-stone-200">{state.recap.lines.map((line, i) => <li key={i}>{line}</li>)}</ul>
        <p className="text-sm text-amber-200">{state.recap.next}</p>
        {!ended && (isHost
          ? <button className={button} disabled={disabled} onClick={() => act("continue")}>Finish the introduction</button>
          : <p className="text-sm text-amber-200">Your host will finish once everyone has read the recap.</p>)}
      </div>}
      {state.phase === "complete" && <div className="space-y-2 text-sm text-stone-300">
        <h3 className="font-semibold text-amber-100">Introduction complete</h3>
        {v5
          ? <p>You made checks, spoke in character, chose a path, and came through a real fight. That’s the rhythm of a session.</p>
          : <p>You chose an approach, rolled a check{state.conversation ? ", spoke with Mara, and chose a destination" : ", and changed the story"}{state.encounter ? ", and practiced combat turns" : ""}. That’s the basic rhythm of play.</p>}
        <p>This introduction ends here. Start a new session from your campaign to try different choices or let another player lead.</p>
      </div>}
    </>}
    {(ended || state?.phase === "complete") && campaignId && <Link className={`${button} inline-block`} href={`/campaigns/${campaignId}`}>Back to campaign</Link>}
  </section>;
}
