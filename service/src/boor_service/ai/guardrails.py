"""The stand-in refusal layer: validate a proposed action against red lines.

A *pure*, deterministic, network-free function — ``check_action`` — that every AI
stand-in action must pass through before it reaches the rules engine. Red lines
are structured (not free text) so the check is auditable and testable without a
model in the loop; the natural-language phrasing a player wrote lives in
``RedLine.note`` and is surfaced in the refusal reason.

Design (per RECRUITER-PRIMER.md #3): responsible-AI governance as a first-class,
tested component. The stand-in loop routes every action here and logs refusals to
the session timeline (that wiring lives in the stand-in slice, not this module).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from boor_service.ai.actions import (
    ActionType,
    Disposition,
    Entity,
    GameState,
    ProposedAction,
    SelfRisk,
)


class RedLineKind(enum.StrEnum):
    """A category of standing constraint a player can set on their stand-in."""

    no_attacking_allies = "no_attacking_allies"
    no_attacking_the_helpless = "no_attacking_the_helpless"
    no_targeting_named = "no_targeting_named"
    no_lethal_self_risk = "no_lethal_self_risk"
    forbid_action_types = "forbid_action_types"


@dataclass(frozen=True)
class RedLine:
    """One structured red line, evaluated deterministically by ``check_action``.

    ``entity_ids`` parameterizes :attr:`RedLineKind.no_targeting_named`;
    ``action_types`` parameterizes :attr:`RedLineKind.forbid_action_types`.
    ``note`` is the player's own phrasing, echoed in the refusal reason.
    """

    kind: RedLineKind
    entity_ids: frozenset[str] = frozenset()
    action_types: frozenset[ActionType] = frozenset()
    note: str = ""


@dataclass(frozen=True)
class Allowed:
    """The action crosses no red line and may be dispatched."""


@dataclass(frozen=True)
class Refused:
    """The action crosses ``red_line``; ``reason`` explains why, for the log."""

    reason: str
    red_line: RedLine


type Decision = Allowed | Refused


def check_action(
    action: ProposedAction,
    red_lines: tuple[RedLine, ...],
    game_state: GameState,
) -> Decision:
    """Return :class:`Allowed`, or :class:`Refused` for the first crossed line.

    Red lines are evaluated in the given order; the first violation wins so the
    result is deterministic for a fixed input.
    """
    for red_line in red_lines:
        reason = _violation_reason(red_line, action, game_state)
        if reason is not None:
            return Refused(reason=_with_note(reason, red_line), red_line=red_line)
    return Allowed()


def _with_note(reason: str, red_line: RedLine) -> str:
    return f'{reason} (red line: "{red_line.note}")' if red_line.note else reason


def _violation_reason(
    red_line: RedLine, action: ProposedAction, game_state: GameState
) -> str | None:
    """Reason string if ``red_line`` is crossed, else ``None``. Pure per-kind logic."""
    match red_line.kind:
        case RedLineKind.no_attacking_allies:
            if action.offensive:
                for entity in _targets(action, game_state):
                    if entity.disposition is Disposition.ally:
                        return f"would take an offensive action against ally {entity.name}"
            return None

        case RedLineKind.no_attacking_the_helpless:
            if action.offensive:
                for entity in _targets(action, game_state):
                    if entity.unconscious:
                        return f"would attack the helpless (unconscious) {entity.name}"
            return None

        case RedLineKind.no_targeting_named:
            if action.offensive:
                for target_id in action.target_ids:
                    if target_id in red_line.entity_ids:
                        target = game_state.entity(target_id)
                        name = target.name if target is not None else target_id
                        return f"would target the off-limits {name}"
            return None

        case RedLineKind.no_lethal_self_risk:
            if action.self_risk is SelfRisk.lethal:
                return "would take an avoidable, likely-lethal risk to self"
            return None

        case RedLineKind.forbid_action_types:
            if action.type in red_line.action_types:
                return f"action type {action.type} is forbidden"
            return None


def _targets(action: ProposedAction, game_state: GameState) -> list[Entity]:
    """The resolved entities an action affects; unknown target ids are skipped."""
    resolved: list[Entity] = []
    for target_id in action.target_ids:
        entity = game_state.entity(target_id)
        if entity is not None:
            resolved.append(entity)
    return resolved
