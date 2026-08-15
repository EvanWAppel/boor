"""Tests for combatant HP state + damage typing (RULES-03 HP, RULES-04 resist).

TDD: written before the implementation.
"""

from __future__ import annotations

import pytest

from boor_service.combat import DAMAGE_TYPES, Combatant, apply_defenses

# --- damage-type constants -------------------------------------------------


def test_damage_types_include_core_5e_set() -> None:
    for t in ("fire", "cold", "slashing", "piercing", "bludgeoning", "necrotic", "radiant"):
        assert t in DAMAGE_TYPES


# --- apply_defenses (resistance/vulnerability/immunity) --------------------


def test_no_defenses_is_unchanged() -> None:
    assert apply_defenses(10, "fire") == 10


def test_resistance_halves_rounding_down() -> None:
    assert apply_defenses(9, "fire", resistances={"fire"}) == 4


def test_vulnerability_doubles() -> None:
    assert apply_defenses(7, "cold", vulnerabilities={"cold"}) == 14


def test_immunity_zeroes() -> None:
    assert apply_defenses(50, "poison", immunities={"poison"}) == 0


def test_immunity_beats_vulnerability() -> None:
    assert apply_defenses(50, "fire", immunities={"fire"}, vulnerabilities={"fire"}) == 0


def test_resistance_and_vulnerability_cancel() -> None:
    # 5e: resistant AND vulnerable to the same type -> treated as neither.
    assert apply_defenses(10, "fire", resistances={"fire"}, vulnerabilities={"fire"}) == 10


def test_defenses_only_apply_to_matching_type() -> None:
    assert apply_defenses(10, "fire", resistances={"cold"}) == 10


def test_untyped_damage_ignores_defenses() -> None:
    assert apply_defenses(10, None, resistances={"fire"}) == 10


def test_apply_defenses_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        apply_defenses(10, "sonic")


# --- Combatant construction ------------------------------------------------


def test_combatant_defaults_to_full_hp() -> None:
    c = Combatant(name="Grog", max_hp=45)
    assert c.current_hp == 45
    assert c.temp_hp == 0
    assert c.is_alive is True
    assert c.is_unconscious is False


def test_combatant_rejects_nonpositive_max_hp() -> None:
    with pytest.raises(ValueError):
        Combatant(name="Nobody", max_hp=0)


# --- taking damage ---------------------------------------------------------


def test_take_damage_reduces_hp_and_returns_dealt() -> None:
    c = Combatant(name="Grog", max_hp=45)
    dealt = c.take_damage(12)
    assert dealt == 12
    assert c.current_hp == 33


def test_take_damage_applies_resistance() -> None:
    c = Combatant(name=" Member", max_hp=30, resistances={"fire"})
    dealt = c.take_damage(11, "fire")
    assert dealt == 5  # 11 // 2
    assert c.current_hp == 25


def test_damage_floors_at_zero_and_marks_unconscious() -> None:
    c = Combatant(name="Grog", max_hp=10)
    dealt = c.take_damage(100)
    assert dealt == 100
    assert c.current_hp == 0
    assert c.is_unconscious is True
    assert c.is_alive is False


def test_temp_hp_absorbs_first() -> None:
    c = Combatant(name="Warded", max_hp=20)
    c.add_temp_hp(8)
    c.take_damage(5)
    assert c.temp_hp == 3
    assert c.current_hp == 20  # untouched while temp remains


def test_temp_hp_overflow_spills_to_hp() -> None:
    c = Combatant(name="Warded", max_hp=20)
    c.add_temp_hp(8)
    c.take_damage(12)
    assert c.temp_hp == 0
    assert c.current_hp == 16  # 12 - 8 spilled over


def test_temp_hp_does_not_stack_takes_higher() -> None:
    c = Combatant(name="Warded", max_hp=20)
    c.add_temp_hp(5)
    c.add_temp_hp(8)
    assert c.temp_hp == 8
    c.add_temp_hp(3)  # lower, ignored
    assert c.temp_hp == 8


def test_take_damage_rejects_negative() -> None:
    c = Combatant(name="Grog", max_hp=10)
    with pytest.raises(ValueError):
        c.take_damage(-1)


# --- healing ---------------------------------------------------------------


def test_heal_restores_up_to_max() -> None:
    c = Combatant(name="Grog", max_hp=45, current_hp=10)
    healed = c.heal(20)
    assert healed == 20
    assert c.current_hp == 30


def test_heal_cannot_exceed_max() -> None:
    c = Combatant(name="Grog", max_hp=45, current_hp=40)
    healed = c.heal(20)
    assert healed == 5
    assert c.current_hp == 45


def test_heal_revives_from_unconscious() -> None:
    c = Combatant(name="Grog", max_hp=45, current_hp=0)
    assert c.is_unconscious is True
    c.heal(1)
    assert c.is_unconscious is False
    assert c.current_hp == 1
