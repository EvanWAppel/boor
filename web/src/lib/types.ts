// Shared types mirroring the FastAPI service's request/response models.
// Kept in sync by hand with service/src/boor_service/api.py — the service is the
// source of truth; these are the web's typed view of it.

export type MembershipRole = "dm" | "player";

export type RiskTolerance = "cautious" | "balanced" | "bold" | "reckless";

export type RedLineKind =
  | "no_attacking_allies"
  | "no_attacking_the_helpless"
  | "no_targeting_named"
  | "no_lethal_self_risk"
  | "forbid_action_types";

export interface Me {
  id: string;
  email: string;
  display_name: string | null;
}

export interface Campaign {
  id: string;
  name: string;
  owner_id: string;
  my_role: MembershipRole;
}

export interface Member {
  user_id: string;
  role: MembershipRole;
  display_name: string | null;
}

export interface Invite {
  id: string;
  token: string;
  email: string;
  role: MembershipRole;
  status: string;
}

export interface AcceptResult {
  campaign_id: string;
  role: MembershipRole;
}

/** The definitional inputs of a 5e sheet (POST body); matches CharacterSheet. */
export interface CharacterCreate {
  name: string;
  level?: number;
  abilities: Record<string, number>;
  max_hp: number;
  skill_proficiencies?: string[];
  skill_expertise?: string[];
  save_proficiencies?: string[];
  base_armor_class?: number | null;
  resistances?: string[];
  immunities?: string[];
  vulnerabilities?: string[];
}

/** The persisted 5e sheet inputs (matches Character.to_sheet on the service). */
export interface CharacterSheet {
  name: string;
  level: number;
  abilities: Record<string, number>;
  max_hp: number;
  skill_proficiencies: string[];
  skill_expertise: string[];
  save_proficiencies: string[];
  base_armor_class: number | null;
  resistances: string[];
  immunities: string[];
  vulnerabilities: string[];
}

export interface Character {
  id: string;
  campaign_id: string;
  player_id: string | null;
  name: string;
  level: number;
  sheet: CharacterSheet;
}

export interface ProfileInput {
  persona?: string;
  standing_instructions?: string;
  risk_tolerance?: RiskTolerance;
  traits?: Record<string, unknown>;
}

export interface Profile {
  character_id: string;
  persona: string;
  standing_instructions: string;
  risk_tolerance: RiskTolerance;
  traits: Record<string, unknown>;
}

export interface RedLineInput {
  kind: RedLineKind;
  entity_ids?: string[];
  action_types?: string[];
  note?: string;
}

export interface RedLine {
  kind: RedLineKind;
  entity_ids: string[];
  action_types: string[];
  note: string;
}

/** A dice roll result from the rules engine (mirrors RollOut). */
export interface RollResult {
  total: number;
  dice: number[];
  modifier: number;
  notation: string;
  dropped: number[];
}

export type SessionStatus = "scheduled" | "active" | "ended";

/** One play session — the room friends join for the theater-of-the-mind table. */
export interface GameSession {
  id: string;
  campaign_id: string;
  title: string | null;
  status: SessionStatus;
  started_at: string | null;
  ended_at: string | null;
}

/** The kinds of entry a session timeline holds (mirrors EventKind). */
export type EventKind =
  | "roll"
  | "action"
  | "move"
  | "turn"
  | "narration"
  | "in_character"
  | "out_of_character"
  | "system";

/** Who may know a session event (DATA-07 / mirrors EventAudience). */
export type EventAudience = "table" | "characters" | "dm";

/** One entry in a session's timeline, as replayed by GET /sessions/{id}/log. */
export interface SessionEvent {
  seq: number;
  kind: EventKind;
  actor_user_id: string | null;
  actor_label: string | null;
  body: string | null;
  payload: Record<string, unknown>;
  ai_generated: boolean;
  audience: EventAudience;
  visible_to: string[];
  created_at: string;
}
