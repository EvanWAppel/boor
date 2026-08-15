"""Character domain model (DATA-02).

Pure in-memory representation of a 5e SRD character: ability scores,
proficiencies, and level, plus the derived stats and the roll helpers that
delegate to :mod:`boor_service.mechanics`. HP state is composed via a
:class:`~boor_service.combat.Combatant`.

No persistence here — how a Character is stored/loaded depends on the datastore
decision (see ``../DECISIONS.md``). This model is deliberately independent of
that choice so it stays reworkable.
"""

from __future__ import annotations

import logging
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field

from boor_service.combat import Combatant
from boor_service.dice import SupportsRandint
from boor_service.mechanics import (
    CheckResult,
    ability_check,
    ability_modifier,
    proficiency_bonus,
)

logger = logging.getLogger(__name__)

# Ability score keys, in canonical 5e order.
ABILITIES: tuple[str, ...] = ("str", "dex", "con", "int", "wis", "cha")

# The 18 SRD skills, each mapped to its governing ability.
SKILLS: dict[str, str] = {
    "athletics": "str",
    "acrobatics": "dex",
    "sleight_of_hand": "dex",
    "stealth": "dex",
    "arcana": "int",
    "history": "int",
    "investigation": "int",
    "nature": "int",
    "religion": "int",
    "animal_handling": "wis",
    "insight": "wis",
    "medicine": "wis",
    "perception": "wis",
    "survival": "wis",
    "deception": "cha",
    "intimidation": "cha",
    "performance": "cha",
    "persuasion": "cha",
}


@dataclass
class Character:
    """A 5e SRD character sheet with derived stats and roll helpers."""

    name: str
    level: int
    abilities: dict[str, int]
    max_hp: int
    skill_proficiencies: AbstractSet[str] = frozenset()
    skill_expertise: AbstractSet[str] = frozenset()
    save_proficiencies: AbstractSet[str] = frozenset()
    base_armor_class: int | None = None
    resistances: AbstractSet[str] = frozenset()
    immunities: AbstractSet[str] = frozenset()
    vulnerabilities: AbstractSet[str] = frozenset()
    combatant: Combatant = field(init=False)

    def __post_init__(self) -> None:
        if not 1 <= self.level <= 20:
            raise ValueError(f"level must be in 1..20: {self.level}")

        missing = set(ABILITIES) - set(self.abilities)
        if missing:
            raise ValueError(f"missing ability scores: {sorted(missing)}")

        unknown_skills = (set(self.skill_proficiencies) | set(self.skill_expertise)) - set(SKILLS)
        if unknown_skills:
            raise ValueError(f"unknown skills: {sorted(unknown_skills)}")

        not_proficient = set(self.skill_expertise) - set(self.skill_proficiencies)
        if not_proficient:
            raise ValueError(f"expertise requires proficiency: {sorted(not_proficient)}")

        unknown_saves = set(self.save_proficiencies) - set(ABILITIES)
        if unknown_saves:
            raise ValueError(f"unknown save abilities: {sorted(unknown_saves)}")

        self.combatant = Combatant(
            name=self.name,
            max_hp=self.max_hp,
            resistances=self.resistances,
            immunities=self.immunities,
            vulnerabilities=self.vulnerabilities,
        )

    # --- derived stats -----------------------------------------------------

    @property
    def proficiency_bonus(self) -> int:
        return proficiency_bonus(self.level)

    def ability_modifier(self, ability: str) -> int:
        if ability not in ABILITIES:
            raise ValueError(f"unknown ability: {ability!r}")
        return ability_modifier(self.abilities[ability])

    def skill_bonus(self, skill: str) -> int:
        """Ability mod + proficiency (doubled for expertise) if applicable."""
        if skill not in SKILLS:
            raise ValueError(f"unknown skill: {skill!r}")
        bonus = self.ability_modifier(SKILLS[skill])
        if skill in self.skill_expertise:
            bonus += self.proficiency_bonus * 2
        elif skill in self.skill_proficiencies:
            bonus += self.proficiency_bonus
        return bonus

    def save_bonus(self, ability: str) -> int:
        bonus = self.ability_modifier(ability)
        if ability in self.save_proficiencies:
            bonus += self.proficiency_bonus
        return bonus

    @property
    def armor_class(self) -> int:
        """Explicit AC if set, else unarmored (10 + DEX mod)."""
        if self.base_armor_class is not None:
            return self.base_armor_class
        return 10 + self.ability_modifier("dex")

    @property
    def initiative_bonus(self) -> int:
        return self.ability_modifier("dex")

    @property
    def passive_perception(self) -> int:
        return 10 + self.skill_bonus("perception")

    # --- rolling (delegates to mechanics) ----------------------------------

    def roll_skill_check(
        self,
        skill: str,
        *,
        dc: int | None = None,
        advantage: bool = False,
        disadvantage: bool = False,
        rng: SupportsRandint | None = None,
    ) -> CheckResult:
        return ability_check(
            self.skill_bonus(skill),
            dc=dc,
            advantage=advantage,
            disadvantage=disadvantage,
            rng=rng,
        )

    def roll_save(
        self,
        ability: str,
        *,
        dc: int | None = None,
        advantage: bool = False,
        disadvantage: bool = False,
        rng: SupportsRandint | None = None,
    ) -> CheckResult:
        if ability not in ABILITIES:
            raise ValueError(f"unknown ability: {ability!r}")
        # save_bonus already folds in proficiency; use ability_check directly so
        # we don't double-count it.
        return ability_check(
            self.save_bonus(ability),
            dc=dc,
            advantage=advantage,
            disadvantage=disadvantage,
            rng=rng,
        )
