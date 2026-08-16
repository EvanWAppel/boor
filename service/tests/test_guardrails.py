"""Tests for the stand-in refusal layer (RECRUITER-PRIMER.md #3).

Pure, fast, no DB/network. One case per red-line category, plus ordering, notes,
and the no-red-lines baseline. These are the audit trail for what the guardrail
protects.
"""

from __future__ import annotations

import pytest

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
    RedLine,
    RedLineKind,
    Refused,
    check_action,
)

HERO = "hero"
ALLY = "cleric"
GOBLIN = "goblin"
BROTHER = "brother"


def _scene() -> GameState:
    return GameState(
        actor_id=HERO,
        entities={
            HERO: Entity(HERO, "Hero", Disposition.self),
            ALLY: Entity(ALLY, "Cleric", Disposition.ally),
            GOBLIN: Entity(GOBLIN, "Goblin", Disposition.enemy),
            BROTHER: Entity(BROTHER, "Brother", Disposition.enemy, unconscious=True),
        },
    )


def _attack(target: str, *, offensive: bool = True) -> ProposedAction:
    return ProposedAction(
        type=ActionType.attack,
        actor_id=HERO,
        target_ids=(target,),
        offensive=offensive,
    )


def test_no_red_lines_allows_everything() -> None:
    decision = check_action(_attack(GOBLIN), (), _scene())
    assert isinstance(decision, Allowed)


def test_offensive_attack_on_enemy_is_allowed() -> None:
    red_lines = (RedLine(kind=RedLineKind.no_attacking_allies),)
    decision = check_action(_attack(GOBLIN), red_lines, _scene())
    assert isinstance(decision, Allowed)


def test_no_attacking_allies_refuses_offensive_action_on_ally() -> None:
    red_lines = (RedLine(kind=RedLineKind.no_attacking_allies, note="never hit friends"),)
    decision = check_action(_attack(ALLY), red_lines, _scene())
    assert isinstance(decision, Refused)
    assert decision.red_line.kind is RedLineKind.no_attacking_allies
    assert "Cleric" in decision.reason
    assert "never hit friends" in decision.reason


def test_non_offensive_action_on_ally_is_allowed() -> None:
    # A heal aimed at an ally is not offensive, so it must not be refused.
    red_lines = (RedLine(kind=RedLineKind.no_attacking_allies),)
    heal = ProposedAction(
        type=ActionType.cast_spell, actor_id=HERO, target_ids=(ALLY,), offensive=False
    )
    assert isinstance(check_action(heal, red_lines, _scene()), Allowed)


def test_no_attacking_allies_flags_aoe_friendly_fire() -> None:
    red_lines = (RedLine(kind=RedLineKind.no_attacking_allies),)
    fireball = ProposedAction(
        type=ActionType.cast_spell,
        actor_id=HERO,
        target_ids=(GOBLIN, ALLY),
        offensive=True,
    )
    decision = check_action(fireball, red_lines, _scene())
    assert isinstance(decision, Refused)
    assert "Cleric" in decision.reason


def test_no_attacking_the_helpless_refuses_unconscious_target() -> None:
    red_lines = (RedLine(kind=RedLineKind.no_attacking_the_helpless),)
    decision = check_action(_attack(BROTHER), red_lines, _scene())
    assert isinstance(decision, Refused)
    assert "helpless" in decision.reason


def test_no_targeting_named_refuses_off_limits_entity() -> None:
    red_lines = (
        RedLine(
            kind=RedLineKind.no_targeting_named,
            entity_ids=frozenset({BROTHER}),
            note="never harm my brother",
        ),
    )
    decision = check_action(_attack(BROTHER), red_lines, _scene())
    assert isinstance(decision, Refused)
    assert "Brother" in decision.reason


def test_no_targeting_named_ignores_others() -> None:
    red_lines = (
        RedLine(kind=RedLineKind.no_targeting_named, entity_ids=frozenset({BROTHER})),
    )
    assert isinstance(check_action(_attack(GOBLIN), red_lines, _scene()), Allowed)


def test_no_lethal_self_risk_refuses_lethal_action() -> None:
    red_lines = (RedLine(kind=RedLineKind.no_lethal_self_risk, note="don't let me die"),)
    reckless = ProposedAction(
        type=ActionType.attack, actor_id=HERO, self_risk=SelfRisk.lethal
    )
    decision = check_action(reckless, red_lines, _scene())
    assert isinstance(decision, Refused)


@pytest.mark.parametrize("risk", [SelfRisk.none, SelfRisk.risky])
def test_no_lethal_self_risk_allows_non_lethal(risk: SelfRisk) -> None:
    red_lines = (RedLine(kind=RedLineKind.no_lethal_self_risk),)
    action = ProposedAction(type=ActionType.attack, actor_id=HERO, self_risk=risk)
    assert isinstance(check_action(action, red_lines, _scene()), Allowed)


def test_forbid_action_types_refuses_listed_type() -> None:
    red_lines = (
        RedLine(
            kind=RedLineKind.forbid_action_types,
            action_types=frozenset({ActionType.flee}),
            note="never abandon the party",
        ),
    )
    flee = ProposedAction(type=ActionType.flee, actor_id=HERO)
    decision = check_action(flee, red_lines, _scene())
    assert isinstance(decision, Refused)
    assert "forbidden" in decision.reason


def test_forbid_action_types_allows_unlisted_type() -> None:
    red_lines = (
        RedLine(
            kind=RedLineKind.forbid_action_types,
            action_types=frozenset({ActionType.flee}),
        ),
    )
    assert isinstance(check_action(_attack(GOBLIN), red_lines, _scene()), Allowed)


def test_first_crossed_red_line_wins() -> None:
    # Order determines which refusal is returned; assert it's deterministic.
    red_lines = (
        RedLine(kind=RedLineKind.no_attacking_the_helpless),
        RedLine(kind=RedLineKind.no_attacking_allies),
    )
    # Brother is an unconscious enemy → the helpless rule (listed first) fires.
    decision = check_action(_attack(BROTHER), red_lines, _scene())
    assert isinstance(decision, Refused)
    assert decision.red_line.kind is RedLineKind.no_attacking_the_helpless


def test_unknown_target_is_not_treated_as_ally() -> None:
    red_lines = (RedLine(kind=RedLineKind.no_attacking_allies),)
    decision = check_action(_attack("ghost"), red_lines, _scene())
    assert isinstance(decision, Allowed)
