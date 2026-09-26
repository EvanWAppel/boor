// Read-only character sheets during play (VTT-08). Shows the party's characters
// with the key numbers a table reaches for — abilities, HP, AC, proficiencies.
// Edits are out of scope for MILE-1 (theater-of-the-mind); this is reference only.

"use client";

import { useState } from "react";

import type { Character } from "@/lib/types";

const ABILITIES = ["str", "dex", "con", "int", "wis", "cha"] as const;

function modifier(score: number): string {
  const mod = Math.floor((score - 10) / 2);
  return mod >= 0 ? `+${mod}` : `${mod}`;
}

function OneSheet({ character }: { character: Character }) {
  const [open, setOpen] = useState(false);
  const sheet = character.sheet;

  return (
    <div className="rounded border border-stone-800">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm"
      >
        <span className="font-medium text-stone-100">{character.name}</span>
        <span className="text-xs text-stone-500">
          Lvl {sheet.level} · {open ? "−" : "+"}
        </span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-stone-800 p-3 text-xs text-stone-300">
          <div className="flex justify-between">
            <span>HP {sheet.max_hp}</span>
            {sheet.base_armor_class != null && <span>AC {sheet.base_armor_class}</span>}
          </div>
          <div className="grid grid-cols-6 gap-1 text-center">
            {ABILITIES.map((a) => (
              <div key={a} className="rounded bg-stone-800 py-1">
                <div className="uppercase text-stone-500">{a}</div>
                <div className="text-stone-100">{sheet.abilities[a] ?? "—"}</div>
                <div className="text-stone-400">
                  {sheet.abilities[a] != null ? modifier(sheet.abilities[a]) : ""}
                </div>
              </div>
            ))}
          </div>
          {sheet.skill_proficiencies.length > 0 && (
            <div>
              <span className="text-stone-500">Proficient: </span>
              {sheet.skill_proficiencies.join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SheetPanel({ characters }: { characters: Character[] }) {
  if (characters.length === 0) {
    return <p className="text-xs text-stone-500 italic">No characters in this campaign yet.</p>;
  }
  return (
    <div className="space-y-2">
      {characters.map((c) => (
        <OneSheet key={c.id} character={c} />
      ))}
    </div>
  );
}
