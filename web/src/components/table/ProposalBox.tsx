// v5 "try something else", shared by check scenes, the Mara conversation, and the fight.
// A playing character proposes a free-form idea; the host (or the AI guide) runs it as
// one of the scene's authored options or replies with a reason. Options and eligibility
// come from lib/guided so they match the server's guard.

"use client";

import { useState } from "react";
import {
  canPropose, canRunCustomCheck, DIFFICULTIES, proposalOptions, SKILL_OPTIONS, type GuidedCommand, type GuidedState,
} from "@/lib/guided";

const button = "rounded-lg border border-amber-700/60 bg-amber-950/50 px-4 py-3 text-left text-sm text-amber-100 hover:bg-amber-900/50 disabled:cursor-not-allowed disabled:opacity-40";
const textarea = "w-full max-w-2xl rounded-lg border border-stone-700 bg-stone-900/60 p-2 text-sm text-stone-100 placeholder:text-stone-500 disabled:opacity-40";

const PLACEHOLDER: Record<string, string> = {
  mara: "e.g. I ask Mara what she's carrying",
  battle: "e.g. I duck behind the cart",
};

export default function ProposalBox({ state, myId, isHost, disabled, ended, act }: {
  state: GuidedState; myId: string | null; isHost: boolean; disabled: boolean; ended: boolean;
  act: (action: GuidedCommand["action"], extra?: Partial<GuidedCommand>) => Promise<boolean> | void;
}) {
  const [proposalText, setProposalText] = useState("");
  const [declineText, setDeclineText] = useState("");
  const [skill, setSkill] = useState("");
  const [dc, setDc] = useState<number | null>(null);
  const [howText, setHowText] = useState("");
  const proposal = state.proposal;
  const scene = state.scene ?? "";

  if (!proposal) {
    if (ended || !canPropose(state, myId)) return null;
    return <div className="space-y-2">
      <label htmlFor="guided-proposal" className="block text-xs text-stone-400">
        Something else in mind? Describe it and the host will decide how to handle it.
      </label>
      <textarea id="guided-proposal" className={textarea} rows={2} maxLength={500} value={proposalText} disabled={disabled}
        placeholder={PLACEHOLDER[scene] ?? "e.g. I look for a plank to wedge under the wheel"} onChange={e => setProposalText(e.target.value)} />
      <button className={button} disabled={disabled || !proposalText.trim()} onClick={() => {
        void Promise.resolve(act("propose", { text: proposalText.trim() })).then(ok => { if (ok) setProposalText(""); });
      }}>Try something else</button>
    </div>;
  }

  const options = proposalOptions(state);
  return <div className="space-y-2 rounded-lg border border-amber-800/60 bg-amber-950/20 p-4">
    <p className="text-sm text-amber-200">{proposal.name} wants to try something else:</p>
    <p className="text-sm italic text-stone-200">“{proposal.text}”</p>
    {proposal.ai === "thinking" && <p role="status" className="text-sm text-sky-200">The AI guide is considering this idea. It can only run it as one of the offered actions{canRunCustomCheck(state) ? ", as its own easy, medium, or hard check," : ""} or explain why not.</p>}
    {proposal.ai === "unavailable" && <p role="status" className="text-sm text-stone-300">The AI guide couldn’t settle this one, so the host will respond.</p>}
    {ended ? null : isHost
      ? <div className="space-y-2">
          <p className="text-xs text-stone-400">{proposal.ai === "thinking" ? "You can answer now instead of waiting; your answer takes precedence. " : ""}Run it as one of the offered actions, or reply with a reason if it isn’t possible here.</p>
          <div className="flex flex-wrap gap-2">
            {options.map(o => <button key={o.id} className={button} disabled={disabled} onClick={() => act("accept_proposal", { approach: o.id })}>Run as {o.label}<br /><span className="text-xs text-stone-400">{o.hint}</span></button>)}
          </div>
          {canRunCustomCheck(state) && <fieldset className="space-y-2 rounded-lg border border-stone-800 p-3">
            <legend className="px-1 text-xs text-stone-400">Or run it as its own check</legend>
            <p className="text-xs text-stone-400">Pick the skill it uses and how hard it is. Success or failure still leads to this scene’s usual outcome.</p>
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-xs text-stone-400" htmlFor="custom-skill">Skill</label>
              <select id="custom-skill" className="rounded-lg border border-stone-700 bg-stone-900/60 p-2 text-sm text-stone-100" value={skill} disabled={disabled} onChange={e => setSkill(e.target.value)}>
                <option value="">Choose a skill…</option>
                {SKILL_OPTIONS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
            </div>
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Difficulty">
              {DIFFICULTIES.map(d => <button key={d.dc} role="radio" aria-checked={dc === d.dc} disabled={disabled}
                className={`${button} ${dc === d.dc ? "border-amber-400 bg-amber-900/60" : ""}`} onClick={() => setDc(d.dc)}>
                {d.label} · {d.dc}<br /><span className="text-xs text-stone-400">{d.hint}</span></button>)}
            </div>
            <input className={textarea} maxLength={300} value={howText} disabled={disabled} placeholder="Optional: how it could play out" onChange={e => setHowText(e.target.value)} />
            <button className={button} disabled={disabled || !skill || dc === null} onClick={() => {
              void Promise.resolve(act("custom_check", { skill, dc: dc ?? undefined, text: howText.trim() || undefined })).then(ok => {
                if (ok) { setSkill(""); setDc(null); setHowText(""); }
              });
            }}>Run as a new check</button>
          </fieldset>}
          <textarea className={textarea} rows={2} maxLength={500} value={declineText} disabled={disabled} placeholder="Reply if this isn’t possible here" onChange={e => setDeclineText(e.target.value)} />
          <button className={button} disabled={disabled || !declineText.trim()} onClick={() => { act("decline_proposal", { text: declineText.trim() }); setDeclineText(""); }}>Send reply instead</button>
        </div>
      : <p role="status" className="text-sm text-amber-200">{proposal.user_id === myId
          ? (proposal.ai === "thinking" ? "Your idea is with the AI guide." : "Your idea is with the host.")
          : (proposal.ai === "thinking" ? "Waiting for the AI guide to respond to the proposal." : "Waiting for the host to respond to the proposal.")}</p>}
  </div>;
}
