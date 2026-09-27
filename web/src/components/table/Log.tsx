// The shared narration log: the unified timeline (chat, OOC, dice, narration),
// newest at the bottom, auto-scrolled. Reads normalized LogEntry rows from useRoom.

"use client";

import { useEffect, useRef } from "react";

import type { LogEntry } from "@/lib/useRoom";

function rollSummary(payload: Record<string, unknown>): string | null {
  const total = payload.total;
  const notation = payload.notation;
  if (typeof total !== "number") return null;
  return typeof notation === "string" ? `${notation} = ${total}` : String(total);
}

function VisibilityMark({ audience }: { audience: LogEntry["audience"] }) {
  if (audience === "table") return null;
  const label = audience === "dm" ? "DM" : "private";
  return (
    <span className="ml-2 rounded bg-stone-800 px-1 text-[10px] uppercase tracking-wide text-stone-400">
      {label}
    </span>
  );
}

function Entry({ entry }: { entry: LogEntry }) {
  const who = entry.label ?? "someone";
  const mark = <>
    {entry.aiGenerated && <span className="ml-2 rounded bg-fuchsia-900/60 px-1 text-[10px] uppercase text-fuchsia-200">AI</span>}
    {entry.payload.allowed === false && <span className="ml-2 text-rose-300">Refused: {String(entry.payload.refusal ?? "Standing boundary")}</span>}
    <VisibilityMark audience={entry.audience} />
  </>;

  if (entry.kind === "turn" && entry.payload.type === "initiative") return null;

  switch (entry.kind) {
    case "in_character":
      return (
        <p className="leading-snug">
          <span className="font-semibold text-amber-200">{who}</span>{" "}
          <span className="text-stone-100">{entry.body}</span>
          {mark}
        </p>
      );
    case "out_of_character":
      return (
        <p className="leading-snug text-stone-400 italic">
          ({who}) {entry.body}
          {mark}
        </p>
      );
    case "roll": {
      const summary = rollSummary(entry.payload);
      return (
        <p className="leading-snug">
          <span className="text-sky-300">🎲 {who}</span>{" "}
          <span className="text-stone-200">{entry.body}</span>
          {summary && (
            <span className="ml-2 font-mono text-sky-200">{summary}</span>
          )}
          {mark}
        </p>
      );
    }
    case "narration":
      return (
        <p className="leading-snug text-emerald-200 italic">
          {entry.body}
          {mark}
        </p>
      );
    default:
      return (
        <p className="leading-snug text-stone-500">
          {entry.body}
          {mark}
        </p>
      );
  }
}

export default function Log({ entries, bounded = false }: { entries: LogEntry[]; bounded?: boolean }) {
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const log = logRef.current;
    if (!log) return;
    if (bounded) log.scrollTop = log.scrollHeight;
    else log.lastElementChild?.scrollIntoView({ block: "end" });
  }, [entries.length, bounded]);

  return (
    <div ref={logRef} className={`flex-1 space-y-1.5 overflow-y-auto p-4 text-sm ${bounded ? "max-h-[32dvh] min-h-24" : ""}`}>
      {entries.length === 0 ? (
        <p className="text-stone-500 italic">
          The table is quiet. Say something in character to begin.
        </p>
      ) : (
        entries.map((e) => <Entry key={e.seq} entry={e} />)
      )}
    </div>
  );
}
