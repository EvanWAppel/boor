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

export interface Character {
  id: string;
  campaign_id: string;
  player_id: string | null;
  name: string;
  level: number;
  sheet: Record<string, unknown>;
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
