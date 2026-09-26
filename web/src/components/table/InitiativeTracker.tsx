// Initiative / turn tracker (VTT-05). The DM builds the order and advances the
// turn; the state is relayed to everyone so the whole table sees whose turn it is.
// Persisted in the session timeline so refreshes and late joins recover it.

"use client";

import { useState } from "react";

import type { InitiativeState } from "@/lib/useRoom";

export default function InitiativeTracker({
  initiative,
  canEdit,
  onChange,
}: {
  initiative: InitiativeState | null;
  canEdit: boolean;
  onChange: (state: InitiativeState) => void;
}) {
  const [name, setName] = useState("");
  const order = initiative?.order ?? [];
  const activeIndex = initiative?.activeIndex ?? 0;

  function add() {
    const n = name.trim();
    if (!n) return;
    onChange({ order: [...order, n], activeIndex });
    setName("");
  }

  function remove(i: number) {
    const next = order.filter((_, idx) => idx !== i);
    onChange({
      order: next,
      activeIndex: next.length ? activeIndex % next.length : 0,
    });
  }

  function nextTurn() {
    if (!order.length) return;
    onChange({ order, activeIndex: (activeIndex + 1) % order.length });
  }

  return (
    <div className="space-y-2">
      {order.length === 0 ? (
        <p className="text-xs text-stone-500 italic">No combat in progress.</p>
      ) : (
        <ol className="space-y-1">
          {order.map((combatant, i) => (
            <li
              key={`${combatant}-${i}`}
              className={`flex items-center justify-between rounded px-2 py-1 text-sm ${
                i === activeIndex
                  ? "bg-amber-800/60 text-amber-100"
                  : "text-stone-300"
              }`}
            >
              <span>
                {i === activeIndex && "▶ "}
                {combatant}
              </span>
              {canEdit && (
                <button
                  type="button"
                  onClick={() => remove(i)}
                  className="text-xs text-stone-500 hover:text-rose-400"
                  aria-label={`Remove ${combatant}`}
                >
                  ✕
                </button>
              )}
            </li>
          ))}
        </ol>
      )}

      {canEdit && (
        <>
          <div className="flex gap-1">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && add()}
              placeholder="Add combatant…"
              className="w-full rounded bg-stone-800 px-2 py-1 text-xs text-stone-100 focus:outline-none focus:ring-1 focus:ring-amber-600"
            />
            <button
              type="button"
              onClick={add}
              className="rounded bg-stone-700 px-2 py-1 text-xs text-stone-100 hover:bg-stone-600"
            >
              +
            </button>
          </div>
          {order.length > 0 && (
            <button
              type="button"
              onClick={nextTurn}
              className="w-full rounded bg-amber-700 px-2 py-1 text-xs font-medium text-amber-50 hover:bg-amber-600"
            >
              Next turn →
            </button>
          )}
        </>
      )}
    </div>
  );
}
