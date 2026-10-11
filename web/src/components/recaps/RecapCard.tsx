// AI-09: one character's session recap, in their own voice. The player can mark it
// read, share it with the table, and flag lines as "not my character" (the text is
// never rewritten); the DM sees flags and can retry a recap that failed to write.

"use client";

import { useState } from "react";

import type { ApiClient } from "@/lib/api";
import { recapStatusLabel } from "@/lib/recaps";
import type { Recap } from "@/lib/types";

const THEMES = {
  // The campaign hub follows the light/dark zinc theme; the table is always dark stone.
  campaign: {
    card: "rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900",
    muted: "text-zinc-500",
    body: "text-zinc-800 dark:text-zinc-100",
    button: "rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-40 dark:border-zinc-700 dark:hover:bg-zinc-800",
    input: "w-full rounded-md border border-zinc-300 bg-transparent p-2 text-sm dark:border-zinc-700",
  },
  table: {
    card: "rounded-lg border border-amber-900/60 bg-stone-900/60 p-4",
    muted: "text-stone-400",
    body: "text-stone-100",
    button: "rounded-md border border-amber-700/60 bg-amber-950/50 px-3 py-1.5 text-sm text-amber-100 hover:bg-amber-900/50 disabled:opacity-40",
    input: "w-full rounded-md border border-stone-700 bg-stone-900/60 p-2 text-sm text-stone-100",
  },
} as const;

export default function RecapCard({ api, recap, isDm, onChange, theme = "campaign" }: {
  api: ApiClient; recap: Recap; isDm: boolean; onChange: (recap: Recap) => void;
  theme?: keyof typeof THEMES;
}) {
  const t = THEMES[theme];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flagging, setFlagging] = useState(false);
  const [quote, setQuote] = useState("");
  const [note, setNote] = useState("");

  async function run(action: () => Promise<Recap>) {
    setBusy(true); setError(null);
    try { onChange(await action()); return true; }
    catch (e) { setError(e instanceof Error ? e.message : "Something went wrong."); return false; }
    finally { setBusy(false); }
  }

  const status = recapStatusLabel(recap, isDm);
  return <article className={`${t.card} space-y-3`} aria-label={`${recap.character_name}'s recap`}>
    <header>
      <p className={`text-xs uppercase tracking-wide ${t.muted}`}>While you were away · {recap.session_title}</p>
      <h3 className={`text-lg font-semibold ${t.body}`}>{recap.character_name}{recap.mine ? " (your character)" : ""}</h3>
      <p className={`text-xs ${t.muted}`}>Written by the AI from what {recap.character_name} saw and did while their stand-in played.{recap.shared ? " Shared with the table." : recap.mine ? " Only you and your DM can see this." : ""}</p>
    </header>
    {recap.status === "ready"
      ? <p className={`whitespace-pre-line leading-relaxed ${t.body}`}>{recap.body}</p>
      : <p role="status" className={`text-sm ${t.muted}`}>{status}{isDm && recap.error ? ` (${recap.error})` : ""}</p>}
    {error && <p role="alert" className="text-sm text-rose-500">{error}</p>}
    <div className="flex flex-wrap gap-2">
      {recap.mine && recap.status === "ready" && !recap.read &&
        <button className={t.button} disabled={busy} onClick={() => run(() => api.markRecapRead(recap.id))}>Mark as read</button>}
      {recap.mine && recap.status === "ready" && !recap.shared &&
        <button className={t.button} disabled={busy} onClick={() => run(() => api.shareRecap(recap.id))}>Share with the table</button>}
      {recap.mine && recap.status === "ready" &&
        <button className={t.button} disabled={busy} aria-expanded={flagging} onClick={() => setFlagging(!flagging)}>Not my character…</button>}
      {isDm && recap.status === "failed" &&
        <button className={t.button} disabled={busy} onClick={() => run(() => api.retryRecap(recap.id))}>Retry recap</button>}
    </div>
    {flagging && <div className="space-y-2">
      <p className={`text-xs ${t.muted}`}>Quote the part that doesn’t sound like your character. The recap stays as it is; your note helps tune your stand-in.</p>
      <input className={t.input} aria-label="Quoted line" maxLength={1000} value={quote} placeholder="Paste the line" onChange={e => setQuote(e.target.value)} />
      <input className={t.input} aria-label="Why it's not your character (optional)" maxLength={1000} value={note} placeholder="Optional: what they'd do or say instead" onChange={e => setNote(e.target.value)} />
      <button className={t.button} disabled={busy || !quote.trim()} onClick={async () => {
        if (await run(() => api.flagRecap(recap.id, quote.trim(), note.trim()))) { setQuote(""); setNote(""); setFlagging(false); }
      }}>Save flag</button>
    </div>}
    {recap.flags.length > 0 && <div className="space-y-1">
      <p className={`text-xs font-medium ${t.muted}`}>Flagged as not {recap.character_name}:</p>
      <ul className={`list-disc space-y-1 pl-5 text-sm ${t.body}`}>
        {recap.flags.map((f, i) => <li key={i}>“{f.quote}”{f.note ? ` — ${f.note}` : ""}</li>)}
      </ul>
    </div>}
  </article>;
}
