import type { GuidedCommand, GuidedState } from "@/lib/guided";

const button = "rounded-lg border border-amber-700/60 bg-amber-950/50 px-4 py-3 text-left text-sm text-amber-100 hover:bg-amber-900/50 disabled:cursor-not-allowed disabled:opacity-40";

export default function ConversationPanel({ state, canPlay, isHost, disabled, ended, act }: {
  state: GuidedState; canPlay: boolean; isHost: boolean; disabled: boolean; ended: boolean;
  act: (action: GuidedCommand["action"], extra?: Partial<GuidedCommand>) => void;
}) {
  const conversation = state.conversation;
  if (!conversation) return null;
  const answered = new Set(conversation.answers.map(a => a.topic));
  return <div className="space-y-4" aria-label="Conversation with Mara">
    <p className="max-w-2xl text-sm leading-relaxed text-stone-300">{conversation.intro}</p>
    {state.phase === "conversation" && <>
      <p className="font-medium text-amber-200">Goal: learn from Mara, then choose your next destination.</p>
      <p className="text-sm text-stone-400">Mara is happy to help. You don’t need to roll to ask a friendly person a question. Any playing character can speak; everyone shares what you learn.</p>
      {!ended && canPlay && <div className="flex flex-wrap gap-2" aria-label="Questions for Mara">
        {conversation.questions.map(q => <button key={q.id} className={button}
          disabled={disabled || answered.has(q.id)} onClick={() => act("ask", { topic: q.id })}>
          {q.label}{answered.has(q.id) ? " · Asked" : ""}
        </button>)}
      </div>}
      {!ended && !canPlay && <p role="status" className="text-sm text-amber-200">You’re watching. The playing characters can ask Mara questions and choose the party’s next stop.</p>}
    </>}
    <div className="space-y-3" aria-live="polite" aria-relevant="additions">
      {conversation.answers.map(a => <div key={a.topic} className="rounded-lg border border-stone-800 bg-stone-900/60 p-4">
        <p className="text-sm text-amber-200">{a.speaker}: {a.question}</p>
        <p className="mt-2 text-sm leading-relaxed text-stone-200"><span className="font-semibold">Mara:</span> {a.reply}</p>
      </div>)}
    </div>
    {!ended && state.phase === "conversation" && canPlay && conversation.answers.length > 0 && <div className="space-y-3">
      <h3 className="font-medium text-stone-100">Where will your party go next?</h3>
      <p className="text-sm text-stone-400">Ask more questions if you like, then agree in chat. One player chooses for the whole party. Once chosen, your destination is set.</p>
      <div className="flex flex-wrap gap-2">
        {conversation.choices.map(c => <button key={c.id} className={button} disabled={disabled}
          onClick={() => act("choose", { choice: c.id })}>{c.label}</button>)}
      </div>
    </div>}
    {conversation.ending && <div className="space-y-2 rounded-lg border border-emerald-900 bg-emerald-950/20 p-4" role="status">
      <h3 className="font-medium text-emerald-200">{conversation.ending.label}</h3>
      <p className="text-xs text-stone-400">Chosen by {conversation.ending.speaker} for the party</p>
      <p className="text-sm leading-relaxed text-stone-200">{conversation.ending.body}</p>
    </div>}
    {!ended && state.phase === "decision" && (isHost
      ? <button className={button} disabled={disabled} onClick={() => act("continue")}>Finish the introduction</button>
      : <p className="text-sm text-amber-200">Your host will finish once everyone has read the ending.</p>)}
    {state.result && <details className="text-sm text-stone-400">
      <summary className="cursor-pointer">Earlier: how the cart rescue went</summary>
      <p className="mt-2">{state.result.outcome}</p>
      <p className="mt-1 font-mono">{state.result.die} {state.result.bonus >= 0 ? "+" : "−"} {Math.abs(state.result.bonus)} = {state.result.total} · target {state.result.dc}</p>
    </details>}
  </div>;
}
