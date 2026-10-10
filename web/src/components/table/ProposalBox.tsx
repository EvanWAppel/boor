// v5 "try something else", shared by check scenes, the Mara conversation, and the fight.
// A playing character proposes a free-form idea; the host (or the AI guide) runs it as
// one of the scene's authored options or replies with a reason. Options and eligibility
// come from lib/guided so they match the server's guard.

"use client";

import { useState } from "react";
import { canPropose, proposalOptions, type GuidedCommand, type GuidedState } from "@/lib/guided";

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
  const proposal = state.proposal;
  const scene = state.scene ?? "";
  if (ended) return null;

  if (!proposal) {
    if (!canPropose(state, myId)) return null;
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
    {proposal.ai === "thinking" && <p role="status" className="text-sm text-sky-200">The AI guide is considering this idea. It can only run it as one of the offered actions or explain why not.</p>}
    {proposal.ai === "unavailable" && <p role="status" className="text-sm text-stone-300">The AI guide couldn’t settle this one, so the host will respond.</p>}
    {isHost
      ? <div className="space-y-2">
          <p className="text-xs text-stone-400">{proposal.ai === "thinking" ? "You can answer now instead of waiting; your answer takes precedence. " : ""}Run it as one of the offered actions, or reply with a reason if it isn’t possible here.</p>
          <div className="flex flex-wrap gap-2">
            {options.map(o => <button key={o.id} className={button} disabled={disabled} onClick={() => act("accept_proposal", { approach: o.id })}>Run as {o.label}<br /><span className="text-xs text-stone-400">{o.hint}</span></button>)}
          </div>
          <textarea className={textarea} rows={2} maxLength={500} value={declineText} disabled={disabled} placeholder="Reply if this isn’t possible here" onChange={e => setDeclineText(e.target.value)} />
          <button className={button} disabled={disabled || !declineText.trim()} onClick={() => { act("decline_proposal", { text: declineText.trim() }); setDeclineText(""); }}>Send reply instead</button>
        </div>
      : <p role="status" className="text-sm text-amber-200">{proposal.user_id === myId
          ? (proposal.ai === "thinking" ? "Your idea is with the AI guide." : "Your idea is with the host.")
          : (proposal.ai === "thinking" ? "Waiting for the AI guide to respond to the proposal." : "Waiting for the host to respond to the proposal.")}</p>}
  </div>;
}
