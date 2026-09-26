"use client";

import { useEffect, useMemo, useState } from "react";
import type { ApiClient } from "@/lib/api";
import type { Character, Profile, RedLine, RedLineKind } from "@/lib/types";
import type { LogEntry } from "@/lib/useRoom";

const rules: [RedLineKind, string][] = [
  ["no_attacking_allies", "Never attack allies"],
  ["no_attacking_the_helpless", "Never attack helpless creatures"],
  ["no_lethal_self_risk", "Avoid lethal personal risk"],
  ["no_targeting_named", "Never target selected characters"],
  ["forbid_action_types", "Never take selected actions"],
];
const actions = ["attack", "cast_spell", "skill_check", "move", "speak", "use_item", "dash", "dodge", "help", "flee", "other"];
const field = "w-full rounded bg-stone-800 p-2 text-xs text-stone-100";

function ProfileEditor({ api, character, party, onClose }: {
  api: ApiClient; character: Character; party: Character[]; onClose: () => void;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [lines, setLines] = useState<RedLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let stopped = false;
    Promise.all([api.getProfile(character.id), api.listRedLines(character.id)])
      .then(([p, r]) => { if (!stopped) { setProfile(p); setLines(r); } })
      .catch(e => { if (!stopped) setError(e.message); });
    return () => { stopped = true; };
  }, [api, character.id]);

  function changeLine(index: number, patch: Partial<RedLine>) {
    setLines(prev => prev.map((line, i) => i === index ? { ...line, ...patch } : line));
  }
  async function save() {
    if (!profile) return;
    setSaving(true); setError(null);
    try {
      await api.saveStandInProfile(character.id, { ...profile, red_lines: lines });
      onClose();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save profile."); }
    finally { setSaving(false); }
  }
  return <div className="space-y-3 border-t border-stone-700 pt-3">
    {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
    {!profile ? <p className="text-xs">Loading personality…</p> : <>
      <label className="block text-xs">Personality and voice
        <textarea className={field} rows={4} value={profile.persona}
          placeholder="What do they want or fear? How do they speak? What matters to them?"
          onChange={e => setProfile({ ...profile, persona: e.target.value })} />
      </label>
      <label className="block text-xs">Standing instructions
        <textarea className={field} rows={3} value={profile.standing_instructions}
          placeholder="What should motivate their decisions while you’re away?"
          onChange={e => setProfile({ ...profile, standing_instructions: e.target.value })} />
      </label>
      <label className="block text-xs">Risk tolerance
        <select className={field} value={profile.risk_tolerance}
          onChange={e => setProfile({ ...profile, risk_tolerance: e.target.value as Profile["risk_tolerance"] })}>
          {["cautious", "balanced", "bold", "reckless"].map(r => <option key={r}>{r}</option>)}
        </select>
      </label>
      <p className="text-xs font-medium">Red lines</p>
      {lines.map((line, i) => <div key={i} className="space-y-2 rounded border border-stone-700 p-2">
        <select aria-label={`Red line ${i + 1}`} className={field} value={line.kind}
          onChange={e => changeLine(i, { kind: e.target.value as RedLineKind })}>
          {rules.map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
        </select>
        {line.kind === "no_targeting_named" && <fieldset className="space-y-1 text-xs"><legend>Protected characters</legend>
          {party.map(c => <label key={c.id} className="block"><input type="checkbox" checked={line.entity_ids.includes(c.id)}
            onChange={e => changeLine(i, { entity_ids: e.target.checked ? [...line.entity_ids, c.id] : line.entity_ids.filter(id => id !== c.id) })} /> {c.name}</label>)}
        </fieldset>}
        {line.kind === "forbid_action_types" && <fieldset className="grid grid-cols-2 gap-1 text-xs"><legend>Forbidden actions</legend>
          {actions.map(a => <label key={a}><input type="checkbox" checked={line.action_types.includes(a)}
            onChange={e => changeLine(i, { action_types: e.target.checked ? [...line.action_types, a] : line.action_types.filter(v => v !== a) })} /> {a.replaceAll("_", " ")}</label>)}
        </fieldset>}
        <input aria-label={`Red line ${i + 1} note`} className={field} placeholder="Your wording (optional)" value={line.note}
          onChange={e => changeLine(i, { note: e.target.value })} />
        <button className="text-xs text-rose-300" onClick={() => setLines(prev => prev.filter((_, n) => n !== i))}>Remove red line</button>
      </div>)}
      <button className="text-xs text-amber-200" onClick={() => setLines(prev => [...prev, { kind: "no_attacking_allies", entity_ids: [], action_types: [], note: "" }])}>+ Add red line</button>
      <div className="flex gap-3 text-xs">
        <button disabled={saving || !profile.persona.trim()} className="rounded bg-amber-700 px-3 py-2 disabled:opacity-50" onClick={save}>{saving ? "Saving…" : "Save personality"}</button>
        <button disabled={saving} onClick={onClose}>Cancel</button>
      </div>
    </>}
  </div>;
}

export default function StandInPanel({ api, sessionId, characters, myId, isDm, connected, entries, thinking }: {
  api: ApiClient; sessionId: string; characters: Character[]; myId: string | null;
  isDm: boolean; connected: boolean; entries: LogEntry[]; thinking: string[];
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const enabled = useMemo(() => {
    const state = new Map<string, boolean>();
    for (const event of entries) if (event.payload.type === "standin_control" && typeof event.payload.character_id === "string") {
      state.set(event.payload.character_id, event.payload.enabled === true);
    }
    return state;
  }, [entries]);
  async function run(id: string, action: () => Promise<unknown>) {
    setBusy(id); setError(null);
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "Could not complete action."); }
    finally { setBusy(null); }
  }
  return <div className="space-y-3 text-stone-300">
    <p className="text-xs text-stone-400">Save a personality, mark the player absent, then the DM can request one AI turn at a time.</p>
    {error && <p role="alert" className="text-xs text-rose-300">{error}</p>}
    {characters.map(c => <div key={c.id} className="space-y-2 rounded border border-stone-700 p-2">
      <p className="text-sm">{c.name} <span className="text-xs text-amber-200">{thinking.includes(c.id) ? "AI is thinking…" : enabled.get(c.id) ? "AI stand-in" : "Player controlled"}</span></p>
      {(isDm || myId === c.player_id) && <div className="flex flex-wrap gap-3 text-xs">
        <button onClick={() => setEditing(editing === c.id ? null : c.id)}>Edit personality</button>
        <button disabled={!connected || !!busy} onClick={() => run(c.id, () => api.setStandIn(sessionId, c.id, !enabled.get(c.id)))}>
          {enabled.get(c.id) ? "Take back control" : "Mark absent · enable AI"}
        </button>
      </div>}
      {isDm && enabled.get(c.id) && <button className="rounded bg-amber-800 px-3 py-2 text-xs disabled:opacity-50"
        disabled={!connected || !!busy || thinking.length > 0}
        onClick={() => run(c.id, () => api.takeStandInTurn(sessionId, c.id, crypto.randomUUID()))}>
        {busy === c.id ? "Working…" : "Request AI turn"}
      </button>}
      {editing === c.id && <ProfileEditor api={api} character={c} party={characters} onClose={() => setEditing(null)} />}
    </div>)}
  </div>;
}
