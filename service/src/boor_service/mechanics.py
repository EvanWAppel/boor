"""5e SRD core mechanics: ability checks & saves (RULES-02) and combat
(RULES-03).

Builds on :mod:`boor_service.dice`. Everything routes its randomness through an
injectable RNG so outcomes are deterministic under test.

Errors are raised, not swallowed — an out-of-range ability score or level is a
real bug the caller should see.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from boor_service.dice import (
    RollResult,
    SupportsRandint,
    parse_notation,
    resolve_rng,
    roll_d20,
)

logger = logging.getLogger(__name__)


def ability_modifier(score: int) -> int:
    """Return the 5e ability modifier for an ability *score* (>= 1)."""
    if score < 1:
        raise ValueError(f"ability score must be >= 1: {score}")
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    """Return the proficiency bonus for a character *level* (1-20)."""
    if not 1 <= level <= 20:
        raise ValueError(f"level must be in 1..20: {level}")
    return 2 + (level - 1) // 4


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a d20 check (ability check, skill check, or saving throw)."""

    roll: RollResult
    total: int
    dc: int | None
    is_success: bool | None


@dataclass(frozen=True)
class AttackResult:
    """Outcome of an attack roll against a target AC."""

    roll: RollResult
    total: int
    ac: int
    is_hit: bool
    is_critical: bool
    is_fumble: bool


def ability_check(
    bonus: int = 0,
    *,
    dc: int | None = None,
    advantage: bool = False,
    disadvantage: bool = False,
    rng: SupportsRandint | None = None,
) -> CheckResult:
    """Roll ``d20 + bonus``; compare to *dc* when supplied.

    A result meeting the DC succeeds (5e: total >= DC).
    """
    d20 = roll_d20(bonus, advantage=advantage, disadvantage=disadvantage, rng=rng)
    is_success = None if dc is None else d20.total >= dc
    logger.debug("ability_check total=%s dc=%s success=%s", d20.total, dc, is_success)
    return CheckResult(roll=d20, total=d20.total, dc=dc, is_success=is_success)


def skill_check(
    *,
    ability_score: int,
    proficient: bool = False,
    expertise: bool = False,
    level: int = 1,
    dc: int | None = None,
    advantage: bool = False,
    disadvantage: bool = False,
    rng: SupportsRandint | None = None,
) -> CheckResult:
    """A skill/ability check: ``d20 + ability mod (+ proficiency)``.

    Expertise doubles the proficiency bonus (and implies proficiency).
    """
    bonus = ability_modifier(ability_score)
    if proficient or expertise:
        prof = proficiency_bonus(level)
        bonus += prof * 2 if expertise else prof
    return ability_check(
        bonus, dc=dc, advantage=advantage, disadvantage=disadvantage, rng=rng
    )


def saving_throw(
    *,
    ability_score: int,
    proficient: bool = False,
    level: int = 1,
    dc: int | None = None,
    advantage: bool = False,
    disadvantage: bool = False,
    rng: SupportsRandint | None = None,
) -> CheckResult:
    """A saving throw: ``d20 + ability mod (+ proficiency if proficient)``."""
    bonus = ability_modifier(ability_score)
    if proficient:
        bonus += proficiency_bonus(level)
    return ability_check(
        bonus, dc=dc, advantage=advantage, disadvantage=disadvantage, rng=rng
    )


def attack_roll(
    bonus: int,
    ac: int,
    *,
    advantage: bool = False,
    disadvantage: bool = False,
    rng: SupportsRandint | None = None,
) -> AttackResult:
    """Resolve an attack roll against *ac*.

    Natural 20 always hits and is a critical; natural 1 always misses (fumble).
    The natural face is the kept die under advantage/disadvantage.
    """
    d20 = roll_d20(bonus, advantage=advantage, disadvantage=disadvantage, rng=rng)
    natural = d20.dice[0]

    if natural == 20:
        is_hit, is_critical, is_fumble = True, True, False
    elif natural == 1:
        is_hit, is_critical, is_fumble = False, False, True
    else:
        is_hit, is_critical, is_fumble = d20.total >= ac, False, False

    logger.debug(
        "attack_roll natural=%s total=%s ac=%s hit=%s crit=%s fumble=%s",
        natural,
        d20.total,
        ac,
        is_hit,
        is_critical,
        is_fumble,
    )
    return AttackResult(
        roll=d20,
        total=d20.total,
        ac=ac,
        is_hit=is_hit,
        is_critical=is_critical,
        is_fumble=is_fumble,
    )


def roll_damage(
    notation: str,
    *,
    critical: bool = False,
    rng: SupportsRandint | None = None,
) -> RollResult:
    """Roll damage dice. On a *critical*, dice are doubled but the flat
    modifier is not (5e crit rule). Damage never drops below 0.
    """
    count, sides, modifier = parse_notation(notation)
    n = count * 2 if critical else count
    rng = resolve_rng(rng)
    faces = tuple(rng.randint(1, sides) for _ in range(n))
    total = max(0, sum(faces) + modifier)
    logger.debug("roll_damage %s critical=%s faces=%s total=%s", notation, critical, faces, total)
    return RollResult(total=total, dice=faces, modifier=modifier, notation=notation)
