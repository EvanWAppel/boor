"""Tests for 5e SRD core mechanics (RULES-02 checks/saves, RULES-03 combat).

TDD: written before the implementation.
"""

from __future__ import annotations

import pytest

from boor_service.mechanics import (
    ability_check,
    ability_modifier,
    attack_roll,
    proficiency_bonus,
    roll_damage,
    saving_throw,
    skill_check,
)
from tests.test_dice import ScriptedRandom

# --- ability modifiers -----------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [(1, -5), (7, -2), (8, -1), (10, 0), (11, 0), (12, 1), (15, 2), (18, 4), (20, 5), (30, 10)],
)
def test_ability_modifier(score: int, expected: int) -> None:
    assert ability_modifier(score) == expected


def test_ability_modifier_rejects_below_one() -> None:
    with pytest.raises(ValueError):
        ability_modifier(0)


# --- proficiency bonus by level -------------------------------------------


@pytest.mark.parametrize(
    ("level", "expected"),
    [(1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (12, 4), (13, 5), (16, 5), (17, 6), (20, 6)],
)
def test_proficiency_bonus(level: int, expected: int) -> None:
    assert proficiency_bonus(level) == expected


@pytest.mark.parametrize("bad", [0, -1, 21])
def test_proficiency_bonus_rejects_out_of_range(bad: int) -> None:
    with pytest.raises(ValueError):
        proficiency_bonus(bad)


# --- generic ability check vs DC ------------------------------------------


def test_ability_check_success_meets_dc() -> None:
    # d20=13 + modifier 2 = 15 vs DC 15 -> success (meets it)
    result = ability_check(bonus=2, dc=15, rng=ScriptedRandom([13]))
    assert result.total == 15
    assert result.dc == 15
    assert result.is_success is True


def test_ability_check_failure_below_dc() -> None:
    result = ability_check(bonus=0, dc=15, rng=ScriptedRandom([10]))
    assert result.total == 10
    assert result.is_success is False


def test_ability_check_without_dc_has_no_verdict() -> None:
    result = ability_check(bonus=3, rng=ScriptedRandom([9]))
    assert result.total == 12
    assert result.dc is None
    assert result.is_success is None


def test_ability_check_advantage() -> None:
    result = ability_check(bonus=1, advantage=True, rng=ScriptedRandom([6, 19]))
    assert result.roll.dice == (19,)
    assert result.total == 20


# --- skill check (ability mod + proficiency, expertise doubles) -----------


def test_skill_check_proficient() -> None:
    # DEX 14 (+2), proficient at level 5 (prof +3): 12 + 2 + 3 = 17
    result = skill_check(ability_score=14, proficient=True, level=5, rng=ScriptedRandom([12]))
    assert result.total == 17


def test_skill_check_not_proficient() -> None:
    # DEX 14 (+2), no proficiency: 12 + 2 = 14
    result = skill_check(ability_score=14, proficient=False, level=5, rng=ScriptedRandom([12]))
    assert result.total == 14


def test_skill_check_expertise_doubles_proficiency() -> None:
    # STR 14 (+2), expertise at level 1 (prof +2 doubled = +4): 10 + 2 + 4 = 16
    result = skill_check(
        ability_score=14, proficient=True, expertise=True, level=1, rng=ScriptedRandom([10])
    )
    assert result.total == 16


def test_skill_check_vs_dc() -> None:
    result = skill_check(
        ability_score=10, proficient=False, level=1, dc=10, rng=ScriptedRandom([9])
    )
    assert result.total == 9
    assert result.is_success is False


# --- saving throw ----------------------------------------------------------


def test_saving_throw_proficient() -> None:
    # CON 16 (+3), proficient at level 9 (prof +4): 8 + 3 + 4 = 15 vs DC 14 -> success
    result = saving_throw(
        ability_score=16, proficient=True, level=9, dc=14, rng=ScriptedRandom([8])
    )
    assert result.total == 15
    assert result.is_success is True


# --- attack rolls ----------------------------------------------------------


def test_attack_hit_meets_ac() -> None:
    # d20=10 + bonus 5 = 15 vs AC 15 -> hit
    result = attack_roll(bonus=5, ac=15, rng=ScriptedRandom([10]))
    assert result.total == 15
    assert result.is_hit is True
    assert result.is_critical is False
    assert result.is_fumble is False


def test_attack_miss_below_ac() -> None:
    result = attack_roll(bonus=0, ac=15, rng=ScriptedRandom([10]))
    assert result.is_hit is False


def test_natural_20_is_critical_hit_regardless_of_ac() -> None:
    result = attack_roll(bonus=-5, ac=30, rng=ScriptedRandom([20]))
    assert result.is_hit is True
    assert result.is_critical is True


def test_natural_1_is_fumble_regardless_of_bonus() -> None:
    result = attack_roll(bonus=100, ac=5, rng=ScriptedRandom([1]))
    assert result.is_hit is False
    assert result.is_fumble is True


def test_attack_crit_uses_kept_die_under_advantage() -> None:
    # advantage keeps the 20 -> critical
    result = attack_roll(bonus=0, ac=18, advantage=True, rng=ScriptedRandom([3, 20]))
    assert result.roll.dice == (20,)
    assert result.is_critical is True


# --- damage ----------------------------------------------------------------


def test_roll_damage_normal() -> None:
    result = roll_damage("2d6+3", rng=ScriptedRandom([4, 5]))
    assert result.dice == (4, 5)
    assert result.total == 12


def test_roll_damage_critical_doubles_dice_not_modifier() -> None:
    # crit on 2d6+3 rolls 4d6, modifier stays +3: 4+5+2+6 + 3 = 20
    result = roll_damage("2d6+3", critical=True, rng=ScriptedRandom([4, 5, 2, 6]))
    assert result.dice == (4, 5, 2, 6)
    assert result.total == 20


def test_roll_damage_minimum_zero() -> None:
    # a big negative modifier never drops damage below 0
    result = roll_damage("1d4-10", rng=ScriptedRandom([1]))
    assert result.total == 0
