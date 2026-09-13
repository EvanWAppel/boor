// Dice roller wired to the rules engine (VTT-04). Rolls are adjudicated by the
// service (/dice/*), then the result is posted to the shared log so the whole
// table — and the durable timeline — sees it.

"use client";

import { useState } from "react";

import type { ApiClient } from "@/lib/api";
import type { RollResult } from "@/lib/types";

const QUICK = ["1d4", "1d6", "1d8", "1d10", "1d12", "1d20", "1d100"];

export default function DiceRoller({
  api,
  onRoll,
  disabled,
}: {
  api: ApiClient | null;
  onRoll: (body: string, payload: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const [notation, setNotation] = useState("1d20");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function roll(n: string, opts?: { advantage?: boolean; disadvantage?: boolean }) {
    if (!api || busy) return;
    setBusy(true);
    setError(null);
    try {
      let result: RollResult;
      let label = `rolls ${n}`;
      if (opts?.advantage || opts?.disadvantage) {
        result = await api.rollD20({ ...opts });
        label = opts.advantage ? "rolls d20 (advantage)" : "rolls d20 (disadvantage)";
      } else {
        result = await api.rollNotation(n);
      }
      onRoll(label, {
        notation: result.notation,
        total: result.total,
        dice: result.dice,
        dropped: result.dropped,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "roll failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {QUICK.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => roll(d)}
            disabled={disabled || busy}
            className="rounded bg-stone-800 px-2 py-1 text-xs font-mono text-stone-200 hover:bg-stone-700 disabled:opacity-40"
          >
            {d}
          </button>
        ))}
      </div>
      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => roll("1d20", { advantage: true })}
          disabled={disabled || busy}
          className="flex-1 rounded bg-emerald-900/70 px-2 py-1 text-xs text-emerald-100 hover:bg-emerald-800 disabled:opacity-40"
        >
          d20 adv
        </button>
        <button
          type="button"
          onClick={() => roll("1d20", { disadvantage: true })}
          disabled={disabled || busy}
          className="flex-1 rounded bg-rose-900/70 px-2 py-1 text-xs text-rose-100 hover:bg-rose-800 disabled:opacity-40"
        >
          d20 dis
        </button>
      </div>
      <div className="flex gap-1">
        <input
          value={notation}
          onChange={(e) => setNotation(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && roll(notation)}
          disabled={disabled || busy}
          placeholder="2d6+3"
          className="w-full rounded bg-stone-800 px-2 py-1 font-mono text-xs text-stone-100 focus:outline-none focus:ring-1 focus:ring-sky-600"
        />
        <button
          type="button"
          onClick={() => roll(notation)}
          disabled={disabled || busy}
          className="rounded bg-sky-800 px-3 py-1 text-xs font-medium text-sky-50 hover:bg-sky-700 disabled:opacity-40"
        >
          Roll
        </button>
      </div>
      {error && <p className="text-xs text-rose-400">{error}</p>}
    </div>
  );
}
