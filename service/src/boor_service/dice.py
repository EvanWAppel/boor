"""5e SRD dice engine (RULES-01).

Parses standard dice notation (``NdM+K``) and resolves d20 rolls with
advantage / disadvantage. Rolls are deterministic when a seeded RNG is
injected, which keeps the engine fully testable.

We deliberately do not catch/convert errors into sentinel values — invalid
notation raises ``ValueError`` so callers (and the AI) see the real failure.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

# NdM (+/- K).  N and the modifier are optional; the die size is required.
_NOTATION = re.compile(
    r"^\s*(?P<count>\d*)d(?P<sides>\d+)\s*(?P<mod>[+-]\s*\d+)?\s*$",
    re.IGNORECASE,
)


class SupportsRandint(Protocol):
    """Anything exposing ``randint(a, b)`` — e.g. ``random.Random``."""

    def randint(self, a: int, b: int) -> int: ...


@dataclass(frozen=True)
class RollResult:
    """Outcome of a dice roll.

    Attributes:
        total: Sum of the counted dice plus the modifier.
        dice: The die faces that counted toward the total.
        modifier: The flat modifier applied (may be negative).
        notation: The notation this result came from.
        dropped: Faces that were rolled but discarded (advantage/disadvantage).
    """

    total: int
    dice: tuple[int, ...]
    modifier: int
    notation: str
    dropped: tuple[int, ...] = field(default=())


def resolve_rng(rng: SupportsRandint | None) -> SupportsRandint:
    return rng if rng is not None else random.Random()


def parse_notation(notation: str) -> tuple[int, int, int]:
    """Parse dice notation into ``(count, sides, modifier)``.

    Raises:
        ValueError: if the notation is malformed or the die has < 1 side.
    """
    match = _NOTATION.match(notation)
    if match is None:
        raise ValueError(f"invalid dice notation: {notation!r}")

    count = int(match["count"]) if match["count"] else 1
    sides = int(match["sides"])
    modifier = int(match["mod"].replace(" ", "")) if match["mod"] else 0

    if count < 1:
        raise ValueError(f"dice count must be >= 1: {notation!r}")
    if sides < 1:
        raise ValueError(f"die must have >= 1 side: {notation!r}")

    return count, sides, modifier


def roll(notation: str, *, rng: SupportsRandint | None = None) -> RollResult:
    """Roll standard dice notation such as ``"2d6+3"`` or ``"d20"``.

    Raises:
        ValueError: if the notation is malformed or the die has < 1 side.
    """
    count, sides, modifier = parse_notation(notation)
    rng = resolve_rng(rng)
    faces = tuple(rng.randint(1, sides) for _ in range(count))
    total = sum(faces) + modifier
    logger.debug("roll %s -> faces=%s modifier=%s total=%s", notation, faces, modifier, total)
    return RollResult(total=total, dice=faces, modifier=modifier, notation=notation)


def roll_d20(
    modifier: int = 0,
    *,
    advantage: bool = False,
    disadvantage: bool = False,
    rng: SupportsRandint | None = None,
) -> RollResult:
    """Roll a d20 with an optional modifier and advantage/disadvantage.

    Per 5e, having both advantage and disadvantage cancels to a straight roll.
    """
    rng = resolve_rng(rng)
    net_adv = advantage != disadvantage  # XOR: cancel when both are set

    if not net_adv:
        first = rng.randint(1, 20)
        return RollResult(
            total=first + modifier,
            dice=(first,),
            modifier=modifier,
            notation="1d20",
        )

    a, b = rng.randint(1, 20), rng.randint(1, 20)
    kept, dropped = (max(a, b), min(a, b)) if advantage else (min(a, b), max(a, b))
    logger.debug(
        "roll_d20 rolled=%s advantage=%s disadvantage=%s kept=%s",
        (a, b),
        advantage,
        disadvantage,
        kept,
    )
    return RollResult(
        total=kept + modifier,
        dice=(kept,),
        modifier=modifier,
        notation="1d20",
        dropped=(dropped,),
    )
