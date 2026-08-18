"""Character domain model (DATA-02).

Pure in-memory representation of a 5e SRD character: ability scores,
proficiencies, and level, plus the derived stats and the roll helpers that
delegate to :mod:`boor_service.mechanics`. HP state is composed via a
:class:`~boor_service.combat.Combatant`.

No datastore coupling here: :meth:`Character.to_sheet` / :meth:`Character.from_sheet`
are pure dict transforms (they serialize the *definitional* inputs, not live combat
state), so the model stays independent of how it's stored. The DB layer persists
the resulting dict as the ``characters.sheet`` JSONB blob (DATA-02).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import Any

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

    # --- persistence (pure dict transforms, no datastore coupling) ---------

    def to_sheet(self) -> dict[str, Any]:
        """A JSON-safe dict of this character's definitional inputs (DATA-02).

        Serializes what *defines* the sheet, not live combat state — current/temp
        HP live in the session, not the character record. Sets become sorted lists
        so the blob is stable. Round-trips with :meth:`from_sheet`.
        """
        return {
            "name": self.name,
            "level": self.level,
            "abilities": dict(self.abilities),
            "max_hp": self.max_hp,
            "skill_proficiencies": sorted(self.skill_proficiencies),
            "skill_expertise": sorted(self.skill_expertise),
            "save_proficiencies": sorted(self.save_proficiencies),
            "base_armor_class": self.base_armor_class,
            "resistances": sorted(self.resistances),
            "immunities": sorted(self.immunities),
            "vulnerabilities": sorted(self.vulnerabilities),
        }

    @classmethod
    def from_sheet(cls, sheet: Mapping[str, Any]) -> Character:
        """Reconstruct a Character from a :meth:`to_sheet` dict (the persisted JSONB).

        Validation (levels, ability completeness, expertise-requires-proficiency)
        is re-run by ``__post_init__``, so a malformed blob raises rather than
        yielding a silently-broken sheet.
        """
        return cls(
            name=sheet["name"],
            level=sheet["level"],
            abilities=dict(sheet["abilities"]),
            max_hp=sheet["max_hp"],
            skill_proficiencies=frozenset(sheet.get("skill_proficiencies", ())),
            skill_expertise=frozenset(sheet.get("skill_expertise", ())),
            save_proficiencies=frozenset(sheet.get("save_proficiencies", ())),
            base_armor_class=sheet.get("base_armor_class"),
            resistances=frozenset(sheet.get("resistances", ())),
            immunities=frozenset(sheet.get("immunities", ())),
            vulnerabilities=frozenset(sheet.get("vulnerabilities", ())),
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
