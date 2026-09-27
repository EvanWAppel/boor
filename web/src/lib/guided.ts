export interface GuidedState {
  version: 1 | 2 | 3 | 4;
  revision: number;
  phase: "lobby" | "ready" | "check" | "outcome" | "conversation" | "decision" | "combat" | "combat_outcome" | "complete";
  intro: string;
  encounter?: PracticeEncounter | null;
  practice_skipped?: boolean;
  conversation?: {
    intro: string;
    questions: { id: "road" | "river" | "mara"; label: string }[];
    choices: { id: "town" | "river"; label: string }[];
    answers: { topic: string; question: string; reply: string; speaker: string; user_id: string }[];
    ending: { choice: string; label: string; body: string; speaker: string; user_id: string } | null;
  } | null;
  seats?: Record<string, { player_name: string; ready: boolean; watching: boolean }>;
  participants: Record<string, { character_id: string; name: string }>;
  pending: { user_id: string; name: string; label: string; skill: string; bonus: number; dc: number } | null;
  result: { die: number; bonus: number; total: number; dc: number; success: boolean; outcome: string } | null;
}
export interface GuidedCommand {
  request_id: string;
  revision: number;
  action: "start" | "select" | "approach" | "roll" | "cancel" | "continue" | "ready" | "unready" | "watch" | "join" | "exclude" | "begin" | "ask" | "choose" | "combat_action" | "stop_practice" | "skip_practice";
  move?: "strike" | "dodge" | "withdraw";
  topic?: "road" | "river" | "mara";
  choice?: "town" | "river";
  target_user_id?: string;
  character_id?: string;
  pregen?: "guardian" | "scholar";
  approach?: "lift" | "leverage";
}

export function isGuidedPayload(payload: Record<string, unknown>): boolean {
  return payload.type === "guided_cart_v1" || payload.type === "guided_cart_v2" || payload.type === "guided_cart_v3" || payload.type === "guided_cart_v4";
}

export interface PracticeEncounter {
  intro: string;
  fighters: Record<string, { name: string; user_id: string | null; hp: number; max_hp: number;
    ac: number; bonus: number; damage: string; initiative: number; dodging: boolean; withdrawn: boolean }>;
  order: string[];
  index: number;
  round: number;
  max_rounds: number;
  messages: string[];
  outcome: { reason: "victory" | "defeat" | "withdrawn" | "limit"; body: string } | null;
}
