"""Tests for the 5e SRD dice engine (RULES-01).

TDD: these describe the desired behaviour before the implementation exists.
"""

from __future__ import annotations

import random

import pytest

from boor_service.dice import RollResult, roll, roll_d20


class ScriptedRandom:
    """A fake RNG that returns a fixed, pre-scripted sequence of faces.

    Lets us assert deterministic outcomes for advantage/disadvantage without
    depending on CPython's Mersenne-Twister internals.
    """

    def __init__(self, faces: list[int]) -> None:
        self._faces = list(faces)

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002 - signature parity
        return self._faces.pop(0)


# --- notation parsing / basic rolls ---------------------------------------


def test_single_die_no_modifier() -> None:
    result = roll("1d20", rng=ScriptedRandom([14]))
    assert result.total == 14
    assert result.dice == (14,)
    assert result.modifier == 0
    assert result.notation == "1d20"


def test_implicit_single_die() -> None:
    # "d8" means "1d8"
    result = roll("d8", rng=ScriptedRandom([5]))
    assert result.total == 5
    assert result.dice == (5,)


def test_multiple_dice_with_positive_modifier() -> None:
    result = roll("2d6+3", rng=ScriptedRandom([4, 6]))
    assert result.dice == (4, 6)
    assert result.modifier == 3
    assert result.total == 13


def test_negative_modifier() -> None:
    result = roll("1d4-1", rng=ScriptedRandom([1]))
    assert result.modifier == -1
    assert result.total == 0


def test_whitespace_and_case_insensitive() -> None:
    result = roll("  2D8 + 2 ", rng=ScriptedRandom([7, 3]))
    assert result.dice == (7, 3)
    assert result.total == 12


@pytest.mark.parametrize("bad", ["", "d", "20", "1d", "1x6", "-1d6", "1d0"])
def test_invalid_notation_raises(bad: str) -> None:
    with pytest.raises(ValueError):
        roll(bad, rng=ScriptedRandom([1, 1, 1]))


# --- randomness bounds (property) -----------------------------------------


def test_rolls_are_within_die_bounds() -> None:
    rng = random.Random(42)
    for _ in range(500):
        r = roll("3d6", rng=rng)
        assert len(r.dice) == 3
        for face in r.dice:
            assert 1 <= face <= 6
        assert r.total == sum(r.dice)


# --- d20 with advantage / disadvantage ------------------------------------


def test_d20_plain() -> None:
    result = roll_d20(modifier=5, rng=ScriptedRandom([12]))
    assert result.dice == (12,)
    assert result.total == 17
    assert result.dropped == ()


def test_d20_advantage_takes_higher() -> None:
    result = roll_d20(modifier=0, advantage=True, rng=ScriptedRandom([8, 17]))
    assert result.dice == (17,)
    assert result.dropped == (8,)
    assert result.total == 17


def test_d20_disadvantage_takes_lower() -> None:
    result = roll_d20(modifier=2, disadvantage=True, rng=ScriptedRandom([8, 17]))
    assert result.dice == (8,)
    assert result.dropped == (17,)
    assert result.total == 10


def test_advantage_and_disadvantage_cancel() -> None:
    # 5e: having both is a straight roll (single d20).
    result = roll_d20(advantage=True, disadvantage=True, rng=ScriptedRandom([11]))
    assert result.dice == (11,)
    assert result.dropped == ()
    assert result.total == 11


def test_result_is_frozen() -> None:
    result = roll("1d6", rng=ScriptedRandom([3]))
    assert isinstance(result, RollResult)
    with pytest.raises((AttributeError, TypeError)):
        result.total = 99  # ty: ignore[invalid-assignment]
