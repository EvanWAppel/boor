"""Pure domain types for an AI stand-in's proposed action and the world it sees.

These are the vocabulary the guardrail layer checks and the stand-in slice will
later fill in from an LLM tool call. Deliberately dependency-free (no DB, no
network) and frozen so they're safe to pass around and cheap to test.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


class Disposition(enum.StrEnum):
    """How an entity relates to the acting character."""

    self = "self"
    ally = "ally"
    enemy = "enemy"
    neutral = "neutral"


class ActionType(enum.StrEnum):
    """The kind of action a stand-in can propose.

    Mirrors what the rules engine can adjudicate; ``offensive`` on the action
    (not the type) decides whether it intends harm, since e.g. a spell can heal
    or hurt.
    """

    attack = "attack"
    cast_spell = "cast_spell"
    skill_check = "skill_check"
    move = "move"
    speak = "speak"
    use_item = "use_item"
    dash = "dash"
    dodge = "dodge"
    help = "help"
    flee = "flee"
    other = "other"


class SelfRisk(enum.StrEnum):
    """How dangerous an action is to the acting character itself."""

    none = "none"
    risky = "risky"
    lethal = "lethal"


@dataclass(frozen=True)
class Entity:
    """A creature/token in the current scene, from the actor's point of view."""

    id: str
    name: str
    disposition: Disposition
    unconscious: bool = False


@dataclass(frozen=True)
class GameState:
    """The slice of scene state the guardrail layer needs to reason about."""

    actor_id: str
    entities: Mapping[str, Entity] = field(default_factory=dict)

    def entity(self, entity_id: str) -> Entity | None:
        """Look up an entity by id, or ``None`` if it isn't in the scene."""
        return self.entities.get(entity_id)


@dataclass(frozen=True)
class ProposedAction:
    """An action a stand-in proposes to take, before adjudication.

    ``offensive`` marks intent to harm the targets (so a heal aimed at an ally
    isn't treated as an attack). ``self_risk`` supports "never let me die if
    avoidable"-style red lines.
    """

    type: ActionType
    actor_id: str
    target_ids: tuple[str, ...] = ()
    offensive: bool = False
    self_risk: SelfRisk = SelfRisk.none
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
