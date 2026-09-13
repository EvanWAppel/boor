// Who's at the table right now (VTT-07). Presence is pushed by the room on every
// join/leave, so this is just a render of the current roster.

"use client";

import type { PresenceEntry } from "@/lib/ws";

export default function Presence({ present }: { present: PresenceEntry[] }) {
  return (
    <div className="space-y-1">
      {present.length === 0 ? (
        <p className="text-xs text-stone-500 italic">No one else is here yet.</p>
      ) : (
        <ul className="space-y-1">
          {present.map((p) => (
            <li key={p.user_id} className="flex items-center gap-2 text-sm text-stone-200">
              <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
              {p.display_name ?? "Anonymous"}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
