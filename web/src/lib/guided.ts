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
  // ai: "thinking" while the AI guide considers it; "unavailable" when the host must answer.
  proposal?: { id?: string; user_id: string; name: string; text: string; ai?: "thinking" | "unavailable" | null } | null;
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

// v5 "try something else": the authored options an open proposal may be mapped onto.
// Ids mirror boor_service.guided_scenes.proposal_options exactly (the server
// re-validates). Check scenes: the offered approaches. Mara: only questions not yet
// asked (the destination stays an explicit choice). Fight: strike a standing enemy,
// dodge, or withdraw.
export interface ProposalOption { id: string; label: string; hint: string }

type ProposalView = Pick<GuidedState, "scene" | "actions" | "conversation" | "encounter">;

export function proposalOptions(state: ProposalView): ProposalOption[] {
  const scene = state.scene ?? "";
  if (CHECK_SCENES.has(scene)) return (state.actions ?? []).map(({ id, label, hint }) => ({ id, label, hint }));
  if (scene === "mara" && state.conversation) {
    const asked = new Set(state.conversation.answers.map(a => a.topic));
    return state.conversation.questions.filter(q => !asked.has(q.id))
      .map(q => ({ id: q.id, label: `Ask Mara: ${q.label}`, hint: "A question; no roll" }));
  }
  if (scene === "battle" && state.encounter) {
    const { order, fighters } = state.encounter;
    const standing = order.filter(id => fighters[id].user_id === null && fighters[id].hp > 0 && !fighters[id].withdrawn);
    return [
      ...standing.map(id => ({ id: `strike:${id}`, label: `Strike the ${fighters[id].name}`, hint: "An attack roll against its armor" })),
      { id: "dodge", label: "Dodge", hint: "Attacks against you have disadvantage until your next turn" },
      { id: "withdraw", label: "Withdraw", hint: "Leave the fight safely" },
    ];
  }
  return [];
}

const PROPOSAL_PHASE: Record<string, GuidedState["phase"]> = { mara: "conversation", battle: "combat" };

/** Whether this person may submit a proposal right now (mirrors the server's guard). */
export function canPropose(
  state: ProposalView & Pick<GuidedState, "version" | "phase" | "participants" | "proposal">, myId: string | null,
): boolean {
  const scene = state.scene ?? "";
  if (state.version < 5 || !myId || !state.participants[myId] || state.proposal) return false;
  const phase = CHECK_SCENES.has(scene) ? "ready" : PROPOSAL_PHASE[scene];
  if (!phase || state.phase !== phase) return false;
  if (scene === "battle") {
    const e = state.encounter;
    return !!e && !e.outcome && e.order[e.index] === myId;
  }
  return proposalOptions(state).length > 0;
}
