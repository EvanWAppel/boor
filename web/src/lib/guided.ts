export interface GuidedState {
  version: 1 | 2;
  revision: number;
  phase: "lobby" | "ready" | "check" | "outcome" | "complete";
  intro: string;
  seats?: Record<string, { player_name: string; ready: boolean; watching: boolean }>;
  participants: Record<string, { character_id: string; name: string }>;
  pending: { user_id: string; name: string; label: string; skill: string; bonus: number; dc: number } | null;
  result: { die: number; bonus: number; total: number; dc: number; success: boolean; outcome: string } | null;
}
export interface GuidedCommand {
  request_id: string;
  revision: number;
  action: "start" | "select" | "approach" | "roll" | "cancel" | "continue" | "ready" | "unready" | "watch" | "join" | "exclude" | "begin";
  target_user_id?: string;
  character_id?: string;
  pregen?: "guardian" | "scholar";
  approach?: "lift" | "leverage";
}

export function isGuidedPayload(payload: Record<string, unknown>): boolean {
  return payload.type === "guided_cart_v1" || payload.type === "guided_cart_v2";
}
