export interface GuidedAction { id: string; label: string; skill: string; hint: string }

export interface GuidedState {
  version: 1 | 2 | 3 | 4 | 5;
  revision: number;
  phase: "lobby" | "ready" | "check" | "outcome" | "conversation" | "decision" | "combat" | "combat_outcome" | "recap" | "complete";
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
  // v5 scene-graph projection (absent on v1-v4 runs).
  scene?: string | null;
  scene_title?: string | null;
  scene_intro?: string | null;
  goal?: string | null;
  actions?: GuidedAction[];
  recap?: { lines: string[]; next: string } | null;
  proposal?: { user_id: string; name: string; text: string } | null;
  paused?: { user_id: string; name: string; note: string | null } | null;
}
export interface GuidedCommand {
  request_id: string;
  revision: number;
  action: "start" | "select" | "approach" | "roll" | "cancel" | "continue" | "ready" | "unready" | "watch" | "join" | "exclude" | "begin" | "ask" | "choose" | "combat_action" | "stop_practice" | "skip_practice" | "propose" | "accept_proposal" | "decline_proposal" | "pause" | "pause_note" | "resume";
  move?: "strike" | "dodge" | "withdraw";
  topic?: "road" | "river" | "mara";
  choice?: "town" | "river";
  target_user_id?: string;
  character_id?: string;
  pregen?: "guardian" | "scholar";
  approach?: string;
  target?: string;
  text?: string;
}

const GUIDED_TYPES = new Set(["guided_cart_v1", "guided_cart_v2", "guided_cart_v3", "guided_cart_v4", "guided_cart_v5"]);
export function isGuidedPayload(payload: Record<string, unknown>): boolean {
  return typeof payload.type === "string" && GUIDED_TYPES.has(payload.type);
}

// v5 pause: anyone seated pauses live play instantly; the pauser or the host resumes.
export function pauseControls(
  state: Pick<GuidedState, "version" | "scene" | "phase" | "seats" | "paused">, myId: string | null, isHost: boolean,
): { canPause: boolean; canResume: boolean; canNote: boolean } {
  const live = state.version >= 5 && !!state.scene && state.phase !== "complete";
  const seated = !!myId && !!state.seats?.[myId];
  const paused = state.paused ?? null;
  const mine = !!paused && paused.user_id === myId;
  return { canPause: live && seated && !paused, canResume: !!paused && (mine || isHost), canNote: mine };
}

// v5 check scenes (as opposed to the conversation, battle, and recap scenes).
export const CHECK_SCENES = new Set(["cart", "gate", "landing"]);

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
