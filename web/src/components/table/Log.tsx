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
  const mark = <VisibilityMark audience={entry.audience} />;

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
          {entry.aiGenerated && (
            <span className="ml-2 rounded bg-fuchsia-900/60 px-1 text-[10px] uppercase tracking-wide text-fuchsia-200">
              AI
            </span>
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

export default function Log({ entries }: { entries: LogEntry[] }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [entries.length]);

  return (
    <div className="flex-1 space-y-1.5 overflow-y-auto p-4 text-sm">
      {entries.length === 0 ? (
        <p className="text-stone-500 italic">
          The table is quiet. Say something in character to begin.
        </p>
      ) : (
        entries.map((e) => <Entry key={e.seq} entry={e} />)
      )}
      <div ref={endRef} />
    </div>
  );
}
