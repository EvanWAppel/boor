"""Combatant HP state and damage typing (RULES-03 HP tracking, RULES-04
resistances / immunities / vulnerabilities).

Pure in-memory game state — no persistence. A :class:`Combatant` is mutable:
combat mutates its HP over the course of an encounter, and each mutating method
returns what actually happened (damage dealt, HP healed) so callers and the log
stay honest.

Errors are raised, not swallowed (negative damage, unknown damage type, etc.).
"""

from __future__ import annotations

import logging
from collections.abc import Set as AbstractSet
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# The 5e SRD damage types.
DAMAGE_TYPES: frozenset[str] = frozenset(
    {
        "acid",
        "bludgeoning",
        "cold",
        "fire",
        "force",
        "lightning",
        "necrotic",
        "piercing",
        "poison",
        "psychic",
        "radiant",
        "slashing",
        "thunder",
    }
)

_FULL_HP_SENTINEL = -1


def _validate_type(damage_type: str) -> None:
    if damage_type not in DAMAGE_TYPES:
        raise ValueError(f"unknown damage type: {damage_type!r}")


def apply_defenses(
    amount: int,
    damage_type: str | None,
    *,
    resistances: AbstractSet[str] = frozenset(),
    immunities: AbstractSet[str] = frozenset(),
    vulnerabilities: AbstractSet[str] = frozenset(),
) -> int:
    """Return *amount* after applying defenses for *damage_type*.

    Order of precedence: immunity (-> 0) beats everything. Being both resistant
    and vulnerable to the same type cancels to normal damage (5e rule).
    Resistance halves (rounded down); vulnerability doubles. Untyped damage
    (``damage_type is None``) ignores all defenses.
    """
    if amount < 0:
        raise ValueError(f"damage amount must be >= 0: {amount}")
    if damage_type is None:
        return amount
    _validate_type(damage_type)

    if damage_type in immunities:
        return 0

    resistant = damage_type in resistances
    vulnerable = damage_type in vulnerabilities
    if resistant and not vulnerable:
        return amount // 2
    if vulnerable and not resistant:
        return amount * 2
    return amount


@dataclass
class Combatant:
    """A creature's mutable HP state during an encounter.

    ``current_hp`` defaults to ``max_hp`` (via the ``-1`` sentinel) so callers
    can spawn a full-health combatant with just a name and ``max_hp``.
    """

    name: str
    max_hp: int
    current_hp: int = _FULL_HP_SENTINEL
    temp_hp: int = 0
    resistances: AbstractSet[str] = frozenset()
    immunities: AbstractSet[str] = frozenset()
    vulnerabilities: AbstractSet[str] = frozenset()

    def __post_init__(self) -> None:
        if self.max_hp < 1:
            raise ValueError(f"max_hp must be >= 1: {self.max_hp}")
        if self.current_hp == _FULL_HP_SENTINEL:
            self.current_hp = self.max_hp
        self.current_hp = max(0, min(self.current_hp, self.max_hp))
        # Normalise defenses to frozensets in case callers pass plain sets.
        self.resistances = frozenset(self.resistances)
        self.immunities = frozenset(self.immunities)
        self.vulnerabilities = frozenset(self.vulnerabilities)

    @property
    def is_unconscious(self) -> bool:
        return self.current_hp == 0

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0

    def add_temp_hp(self, amount: int) -> None:
        """Grant temporary HP. Temp HP does not stack — keep the higher value."""
        if amount < 0:
            raise ValueError(f"temp HP must be >= 0: {amount}")
        self.temp_hp = max(self.temp_hp, amount)

    def take_damage(self, amount: int, damage_type: str | None = None) -> int:
        """Apply damage (after defenses). Temp HP absorbs first, then HP.

        Returns the damage actually dealt after resistances/immunities.
        """
        effective = apply_defenses(
            amount,
            damage_type,
            resistances=self.resistances,
            immunities=self.immunities,
            vulnerabilities=self.vulnerabilities,
        )

        absorbed = min(self.temp_hp, effective)
        self.temp_hp -= absorbed
        remaining = effective - absorbed
        self.current_hp = max(0, self.current_hp - remaining)

        logger.debug(
            "%s takes %s (%s) -> hp=%s temp=%s",
            self.name,
            effective,
            damage_type or "untyped",
            self.current_hp,
            self.temp_hp,
        )
        return effective

    def heal(self, amount: int) -> int:
        """Restore HP up to ``max_hp``. Returns the HP actually restored."""
        if amount < 0:
            raise ValueError(f"heal amount must be >= 0: {amount}")
        before = self.current_hp
        self.current_hp = min(self.max_hp, self.current_hp + amount)
        healed = self.current_hp - before
        logger.debug("%s heals %s -> hp=%s", self.name, healed, self.current_hp)
        return healed
