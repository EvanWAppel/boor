// A minimal 5e character-creation form: enough to seat a real PC at the table
// (name, level, HP, the six ability scores, optional AC). Inventory/spells/skills
// ride in the JSONB sheet later; this is the front-door slice so a player can join
// a session with a sheet the party panel can render.

"use client";

import { useState } from "react";

import type { CharacterCreate } from "@/lib/types";

import { Button, Card, ErrorText, TextInput } from "../ui";

const ABILITIES = ["str", "dex", "con", "int", "wis", "cha"] as const;
type Ability = (typeof ABILITIES)[number];

const ABILITY_LABELS: Record<Ability, string> = {
  str: "STR",
  dex: "DEX",
  con: "CON",
  int: "INT",
  wis: "WIS",
  cha: "CHA",
};

export default function NewCharacterForm({
  onCreate,
}: {
  onCreate: (character: CharacterCreate) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [level, setLevel] = useState(1);
  const [maxHp, setMaxHp] = useState(10);
  const [ac, setAc] = useState<number | "">("");
  const [abilities, setAbilities] = useState<Record<Ability, number>>({
    str: 10,
    dex: 10,
    con: 10,
    int: 10,
    wis: 10,
    cha: 10,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        + Add a character
      </Button>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setSaving(true);
    setError(null);
    try {
      await onCreate({
        name: trimmed,
        level,
        max_hp: maxHp,
        abilities,
        base_armor_class: ac === "" ? null : ac,
      });
      // Reset for a possible next character.
      setName("");
      setLevel(1);
      setMaxHp(10);
      setAc("");
      setAbilities({ str: 10, dex: 10, con: 10, int: 10, wis: 10, cha: 10 });
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to create character");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <label className="col-span-2 flex flex-col gap-1 text-xs text-zinc-500 sm:col-span-2">
            Name
            <TextInput
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Character name"
              autoFocus
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-zinc-500">
            Level
            <TextInput
              type="number"
              min={1}
              max={20}
              value={level}
              onChange={(e) => setLevel(Math.max(1, Number(e.target.value) || 1))}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-zinc-500">
            Max HP
            <TextInput
              type="number"
              min={1}
              value={maxHp}
              onChange={(e) => setMaxHp(Math.max(1, Number(e.target.value) || 1))}
            />
          </label>
        </div>

        <div>
          <p className="mb-1 text-xs text-zinc-500">Ability scores</p>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
            {ABILITIES.map((ability) => (
              <label key={ability} className="flex flex-col gap-1 text-center text-xs text-zinc-500">
                {ABILITY_LABELS[ability]}
                <TextInput
                  type="number"
                  min={1}
                  max={30}
                  value={abilities[ability]}
                  onChange={(e) =>
                    setAbilities((prev) => ({
                      ...prev,
                      [ability]: Math.max(1, Number(e.target.value) || 1),
                    }))
                  }
                  className="text-center"
                />
              </label>
            ))}
          </div>
        </div>

        <label className="flex flex-col gap-1 text-xs text-zinc-500">
          Armor class (optional — defaults to 10 + DEX)
          <TextInput
            type="number"
            min={1}
            value={ac}
            onChange={(e) => setAc(e.target.value === "" ? "" : Number(e.target.value))}
            placeholder="auto"
            className="w-32"
          />
        </label>

        <ErrorText>{error}</ErrorText>

        <div className="flex gap-2">
          <Button type="submit" disabled={saving || !name.trim()}>
            {saving ? "Saving…" : "Create character"}
          </Button>
          <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}
