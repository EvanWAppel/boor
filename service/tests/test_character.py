"""Tests for the Character domain model (DATA-02, pure in-memory).

TDD: written before the implementation. Ties ability scores + proficiencies +
level into derived stats and delegates rolls to boor_service.mechanics.
"""

from __future__ import annotations

import pytest

from boor_service.character import ABILITIES, SKILLS, Character
from tests.test_dice import ScriptedRandom


def make_char(
    *,
    name: str = "Grog",
    level: int = 5,
    abilities: dict[str, int] | None = None,
    max_hp: int = 44,
    skill_proficiencies: frozenset[str] = frozenset(),
    skill_expertise: frozenset[str] = frozenset(),
    save_proficiencies: frozenset[str] = frozenset(),
    base_armor_class: int | None = None,
) -> Character:
    """A representative level-5 fighter-ish sheet, override fields as needed."""
    if abilities is None:
        abilities = {"str": 15, "dex": 14, "con": 13, "int": 12, "wis": 10, "cha": 8}
    return Character(
        name=name,
        level=level,
        abilities=abilities,
        max_hp=max_hp,
        skill_proficiencies=skill_proficiencies,
        skill_expertise=skill_expertise,
        save_proficiencies=save_proficiencies,
        base_armor_class=base_armor_class,
    )


# --- constants -------------------------------------------------------------


def test_ability_and_skill_constants() -> None:
    assert ABILITIES == ("str", "dex", "con", "int", "wis", "cha")
    # a few representative skill -> ability mappings
    assert SKILLS["athletics"] == "str"
    assert SKILLS["stealth"] == "dex"
    assert SKILLS["arcana"] == "int"
    assert SKILLS["perception"] == "wis"
    assert SKILLS["persuasion"] == "cha"
    assert len(SKILLS) == 18


# --- construction / validation --------------------------------------------


def test_requires_all_six_abilities() -> None:
    with pytest.raises(ValueError):
        Character(name="x", level=1, abilities={"str": 10}, max_hp=10)


def test_rejects_bad_level() -> None:
    with pytest.raises(ValueError):
        make_char(level=0)


def test_expertise_must_be_a_subset_of_proficiency() -> None:
    with pytest.raises(ValueError):
        make_char(skill_expertise=frozenset({"stealth"}))  # not proficient in stealth


def test_rejects_unknown_skill() -> None:
    with pytest.raises(ValueError):
        make_char(skill_proficiencies=frozenset({"juggling"}))


def test_rejects_unknown_save_ability() -> None:
    with pytest.raises(ValueError):
        make_char(save_proficiencies=frozenset({"luck"}))


# --- derived stats ---------------------------------------------------------


def test_ability_modifiers() -> None:
    c = make_char()
    assert c.ability_modifier("str") == 2
    assert c.ability_modifier("cha") == -1


def test_proficiency_bonus_from_level() -> None:
    assert make_char(level=5).proficiency_bonus == 3
    assert make_char(level=1).proficiency_bonus == 2


def test_skill_bonus_proficient() -> None:
    c = make_char(skill_proficiencies=frozenset({"athletics"}))
    assert c.skill_bonus("athletics") == 5  # str +2 + prof +3


def test_skill_bonus_not_proficient() -> None:
    assert make_char().skill_bonus("athletics") == 2  # just str +2


def test_skill_bonus_expertise() -> None:
    c = make_char(
        skill_proficiencies=frozenset({"athletics"}),
        skill_expertise=frozenset({"athletics"}),
    )
    assert c.skill_bonus("athletics") == 8  # str +2 + 2*prof(3)


def test_save_bonus_proficient_vs_not() -> None:
    c = make_char(save_proficiencies=frozenset({"str", "con"}))
    assert c.save_bonus("str") == 5  # +2 + prof 3
    assert c.save_bonus("dex") == 2  # +2, no proficiency


def test_default_armor_class_is_unarmored() -> None:
    assert make_char().armor_class == 12  # 10 + dex +2


def test_explicit_armor_class_overrides() -> None:
    assert make_char(base_armor_class=18).armor_class == 18


def test_initiative_bonus_is_dex_mod() -> None:
    assert make_char().initiative_bonus == 2


def test_passive_perception() -> None:
    # unproficient wis 10 -> 10 + 0 = 10
    assert make_char().passive_perception == 10
    # proficient perception at level 5 -> 10 + (0 + 3)
    c = make_char(skill_proficiencies=frozenset({"perception"}))
    assert c.passive_perception == 13


# --- rolling (delegates to mechanics) -------------------------------------


def test_roll_skill_check_uses_bonus() -> None:
    c = make_char(skill_proficiencies=frozenset({"athletics"}))
    result = c.roll_skill_check("athletics", dc=15, rng=ScriptedRandom([12]))
    assert result.total == 17  # 12 + 5
    assert result.is_success is True


def test_roll_save_uses_bonus() -> None:
    c = make_char(save_proficiencies=frozenset({"con"}))
    result = c.roll_save("con", dc=12, rng=ScriptedRandom([9]))
    assert result.total == 13  # 9 + con(+1) + prof(3)
    assert result.is_success is True


# --- HP state via composed combatant --------------------------------------


def test_combatant_starts_at_full_hp() -> None:
    c = make_char()
    assert c.combatant.max_hp == 44
    assert c.combatant.current_hp == 44


def test_taking_damage_tracks_on_character() -> None:
    c = make_char()
    c.combatant.take_damage(10)
    assert c.combatant.current_hp == 34
