"""AI stand-in layer for boor.

The core bet (see ``README.md`` for the full design): a bounded LLM
actor that reasons about the game, but whose *actions are adjudicated by the
deterministic rules engine* — the LLM never invents a die result. Every proposed
action is validated against the character's standing red lines *before* dispatch
(:mod:`boor_service.ai.guardrails`).

This module is intentionally free of any network/LLM dependency; the domain types
here are pure so the guardrail layer is trivially testable and auditable.
"""

from __future__ import annotations

from boor_service.ai.actions import (
    ActionType,
    Disposition,
    Entity,
    GameState,
    ProposedAction,
    SelfRisk,
)
from boor_service.ai.guardrails import (
    Allowed,
    Decision,
    RedLine,
    RedLineKind,
    Refused,
    check_action,
)

__all__ = [
    "ActionType",
    "Allowed",
    "Decision",
    "Disposition",
    "Entity",
    "GameState",
    "ProposedAction",
    "RedLine",
    "RedLineKind",
    "Refused",
    "SelfRisk",
    "check_action",
]
