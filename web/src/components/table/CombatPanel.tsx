import type { GuidedCommand, GuidedState } from "@/lib/guided";

const button = "rounded-lg border border-amber-700/60 bg-amber-950/50 px-4 py-3 text-left text-sm text-amber-100 hover:bg-amber-900/50 disabled:cursor-not-allowed disabled:opacity-40";

export default function CombatPanel({ state, myId, isHost, disabled, ended, act }: {
  state: GuidedState; myId: string | null; isHost: boolean; disabled: boolean; ended: boolean;
  act: (action: GuidedCommand["action"], extra?: Partial<GuidedCommand>) => void;
}) {
  const encounter = state.encounter;
  if (!encounter) return null;
  const v5 = state.version >= 5;
  const hpNoun = v5 ? "HP" : "practice HP";
  const active = encounter.outcome ? null : encounter.order[encounter.index];
  const mine = myId ? encounter.fighters[myId] : null;
  const enemies = encounter.order.filter(id => encounter.fighters[id].user_id === null && encounter.fighters[id].hp > 0);
  return <section className="space-y-4" aria-label={v5 ? "Encounter" : "Practice encounter"}>
    <p className="text-sm leading-relaxed text-stone-300">{encounter.intro}</p>
    <p className="text-sm text-stone-400">Initiative decides who goes first. On your turn, choose one action; the enemies act automatically. HP measures how much more you can take. At zero {hpNoun} you sit out{v5 ? " the rest of the fight" : ", and everyone recovers after the lesson"}.</p>
    <p className="text-xs text-stone-400">{v5 ? "Movement, spells, and death saves are outside this introduction; no one comes to lasting harm." : "This short lesson uses supplied practice staffs and your character’s defenses. Movement, spells, and death saves are outside this lesson."} It ends after at most {encounter.max_rounds} rounds.</p>
    <h3 className="font-medium text-amber-200">Round {Math.min(encounter.round, encounter.max_rounds)} · Turn order</h3>
    <ol className="space-y-2" aria-label="Turn order">
      {encounter.order.map(id => {
        const f = encounter.fighters[id];
        return <li key={id} className={`rounded-lg border p-3 text-sm ${active === id ? "border-amber-600 bg-amber-950/30" : "border-stone-800"}`}>
          <div className="flex flex-wrap justify-between gap-2"><span className="font-medium text-stone-100">{f.name}{id === myId ? " (you)" : ""}{f.user_id === null ? " · foe" : ""}{active === id ? " · Acting now" : ""}</span><span className="font-mono text-stone-300">{f.hp}/{f.max_hp} {hpNoun}</span></div>
          <p className="mt-1 text-xs text-stone-400">Initiative {f.initiative} · Armor class {f.ac}{f.withdrawn ? " · Withdrew" : f.hp === 0 ? " · Out" : f.dodging ? " · Dodging" : ""}</p>
        </li>;
      })}
    </ol>
    {!ended && !encounter.outcome && <>
      {active === myId && mine ? <>
        <h3 className="font-medium text-amber-200">Your turn: {mine.name}</h3>
        <p className="text-sm text-stone-300">An attack rolls a twenty-sided die and applies your attack bonus. Meet the target’s armor class to hit, then roll damage. Your attack bonus is {mine.bonus >= 0 ? "+" : ""}{mine.bonus}; damage {mine.damage}. The app does the math.</p>
        <div className="flex flex-wrap gap-2">
          {enemies.map(id => <button key={id} className={button} disabled={disabled} onClick={() => act("combat_action", { move: "strike", target: id })}>Strike {encounter.fighters[id].name}<br /><span className="text-xs text-stone-400">Attack bonus {mine.bonus >= 0 ? "+" : ""}{mine.bonus} · damage {mine.damage}</span></button>)}
          <button className={button} disabled={disabled} onClick={() => act("combat_action", { move: "dodge" })}>Dodge<br /><span className="text-xs text-stone-400">Attacks against you keep the lower of two dice until your next turn</span></button>
          <button className={button} disabled={disabled} onClick={() => act("combat_action", { move: "withdraw" })}>{v5 ? "Withdraw" : "Withdraw from practice"}<br /><span className="text-xs text-stone-400">Leave safely; your companions can keep {v5 ? "fighting" : "playing"}</span></button>
        </div>
      </> : <p role="status" className="text-sm text-amber-200">Waiting for {active ? encounter.fighters[active].name : "the next turn"}. {mine?.withdrawn || mine?.hp === 0 ? `You’re sitting out this ${v5 ? "fight" : "bout"}.` : "You can follow the action and talk in chat."}</p>}
      {isHost && <button className="text-xs text-stone-400 underline disabled:opacity-40" disabled={disabled} onClick={() => act("stop_practice")}>{v5 ? "Stop the fight for everyone" : "Stop practice for everyone"}</button>}
    </>}
    <div className="space-y-2 text-sm text-stone-200" aria-live="polite">
      {encounter.messages.filter(m => m !== encounter.outcome?.body).map((m, i) => <p key={i}>{m}</p>)}
    </div>
    {encounter.outcome && <div role="status" className="rounded-lg border border-emerald-900 bg-emerald-950/20 p-4 text-sm text-emerald-200">{encounter.outcome.body}</div>}
    {!ended && state.phase === "combat_outcome" && (isHost
      ? <button className={button} disabled={disabled} onClick={() => act("continue")}>{v5 ? "Continue" : "Finish the introduction"}</button>
      : <p className="text-sm text-amber-200">Your host will {v5 ? "continue" : "finish"} after everyone reads the result.</p>)}
    <details className="text-sm text-stone-400"><summary className="cursor-pointer">Earlier: your party’s destination</summary><p className="mt-2">{state.conversation?.ending?.body}</p></details>
  </section>;
}
