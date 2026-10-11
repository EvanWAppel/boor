// AI-09 recaps on the web: what must be read before the table, and status wording.
// Decided 2026-10-10: in-app delivery, shown before the player's next session.

import type { Recap } from "./types";

/** My finished recaps I haven't read yet: shown before I sit down at the table. */
export function recapsToReadFirst<T extends Pick<Recap, "status" | "mine" | "read">>(recaps: T[]): T[] {
  return recaps.filter(r => r.status === "ready" && r.mine && !r.read);
}

export function recapStatusLabel(recap: Pick<Recap, "status">, isDm: boolean): string {
  if (recap.status === "pending") return "This recap is being written. Check back in a minute.";
  if (recap.status === "failed") {
    return isDm ? "This recap couldn’t be written. You can retry it." : "This recap couldn’t be written yet. Your DM can try again.";
  }
  return "";
}
