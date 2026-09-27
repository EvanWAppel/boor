export interface GuidedState {
  version: 1;
  revision: number;
  phase: "ready" | "check" | "outcome" | "complete";
  intro: string;
  participants: Record<string, { character_id: string; name: string }>;
  pending: { user_id: string; name: string; label: string; skill: string; bonus: number; dc: number } | null;
  result: { die: number; bonus: number; total: number; dc: number; success: boolean; outcome: string } | null;
}
export interface GuidedCommand {
  request_id: string;
  revision: number;
  action: "start" | "select" | "approach" | "roll" | "cancel" | "continue";
  character_id?: string;
  pregen?: "guardian" | "scholar";
  approach?: "lift" | "leverage";
}
