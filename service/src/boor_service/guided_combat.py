"""Bounded encounters; pure snapshot transitions over the existing rules engine.

Two entry points share one turn engine:

* ``start_encounter`` — the v4 Mara sparring lesson (single opponent, no targeting).
* ``start_battle`` — the v5 authored encounter (a roster of enemies + target choice).

Enemy fighters are the ones with ``user_id is None``. Encounter HP is scoped to the
snapshot and never written back into character sheets. Randomness is injectable for
deterministic turn/attack/defense tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from boor_service.character import Character
from boor_service.combat import Combatant
from boor_service.dice import SupportsRandint, roll_d20
from boor_service.mechanics import attack_roll, roll_damage

MAX_ROUNDS = 5
MARA = "mara"


@dataclass(frozen=True)
class Enemy:
    """An authored opponent stat block. Keys must be unique within an encounter."""

    key: str
    name: str
    hp: int
    ac: int
    bonus: int
    damage: str
    initiative_bonus: int = 0


def _player_fighter(
    user_id: str, character_id: str, sheet: Character, rng: SupportsRandint | None
) -> dict[str, Any]:
    modifier = max(sheet.ability_modifier("str"), sheet.ability_modifier("dex"))
    return dict(
        user_id=user_id,
        character_id=character_id,
        name=sheet.name,
        hp=sheet.max_hp,
        max_hp=sheet.max_hp,
        ac=sheet.armor_class,
        bonus=modifier + sheet.proficiency_bonus,
        damage=f"1d6{modifier:+}",
        initiative=roll_d20(sheet.initiative_bonus, rng=rng).total,
        dodging=False,
        withdrawn=False,
        resistances=sorted(sheet.resistances),
        immunities=sorted(sheet.immunities),
        vulnerabilities=sorted(sheet.vulnerabilities),
    )


def _enemy_fighter(enemy: Enemy, rng: SupportsRandint | None) -> dict[str, Any]:
    return dict(
        name=enemy.name,
        user_id=None,
        hp=enemy.hp,
        max_hp=enemy.hp,
        ac=enemy.ac,
        bonus=enemy.bonus,
        damage=enemy.damage,
        initiative=roll_d20(enemy.initiative_bonus, rng=rng).total,
        dodging=False,
        withdrawn=False,
        resistances=[],
        immunities=[],
        vulnerabilities=[],
    )


# Transient wording that differs between the practice lesson and a real fight. The
# outcome text lives in ``descriptions``; these cover the moment-to-moment lines so an
# in-flight v4 sparring run keeps its exact phrasing.
_SPARRING_LABELS = {
    "hp": "practice HP",
    "down": "sits out the rest of the bout",
    "stop": "practice bout",
}
_BATTLE_LABELS = {"hp": "HP", "down": "is out of the fight", "stop": "encounter"}

# The v4 encounter dict predates the ``descriptions``/``labels`` keys, so an in-flight
# sparring bout persisted before this change has neither. Only sparring can be mid-flight
# at that shape, so these sparring defaults are the safe fallback for such old snapshots.
_SPARRING_RECOVER = " Everyone recovers after practice; your character sheets are unchanged."
_SPARRING_DESCRIPTIONS = {
    "victory": "Mara yields with a grin. Your party won the practice bout." + _SPARRING_RECOVER,
    "defeat": "Mara lowers her staff and helps you up. The lesson ends safely." + _SPARRING_RECOVER,
    "withdrawn": "Your party stops the practice bout. Stepping away is a useful choice."
    + _SPARRING_RECOVER,
    "limit": "Mara calls time after five rounds. You have practiced taking turns."
    + _SPARRING_RECOVER,
}


def _assemble(
    fighters: dict[str, Any],
    *,
    intro: str,
    descriptions: dict[str, str],
    labels: dict[str, str],
    rng: SupportsRandint | None,
) -> dict[str, Any]:
    order = sorted(fighters, key=lambda key: (-fighters[key]["initiative"], key))
    encounter: dict[str, Any] = dict(
        intro=intro,
        fighters=fighters,
        order=order,
        index=0,
        round=1,
        max_rounds=MAX_ROUNDS,
        outcome=None,
        messages=[intro, "Initiative rolls set the turn order."],
        descriptions=descriptions,
        labels=labels,
    )
    _settle(encounter, rng)
    return encounter


def start_encounter(
    party: list[tuple[str, str, Character]],
    route: str,
    *,
    rng: SupportsRandint | None = None,
) -> dict[str, Any]:
    if not party:
        raise ValueError("At least one playing character is needed for practice.")
    fighters: dict[str, Any] = {
        user_id: _player_fighter(user_id, character_id, sheet, rng)
        for user_id, character_id, sheet in party
    }
    mara = Enemy(
        MARA, "Mara", hp=8 + 4 * len(party), ac=12, bonus=3, damage="1d4+1", initiative_bonus=1
    )
    fighters[MARA] = _enemy_fighter(mara, rng)
    location = (
        "In a quiet yard in Emberlow" if route == "town" else "Before you take the river trail"
    )
    intro = (
        f"{location}, Mara offers a short sparring lesson with padded practice staffs. "
        "Take turns, watch your practice HP, and stop whenever you like."
    )
    return _assemble(
        fighters, intro=intro, descriptions=_SPARRING_DESCRIPTIONS, labels=_SPARRING_LABELS, rng=rng
    )


def start_battle(
    party: list[tuple[str, str, Character]],
    enemies: list[Enemy],
    *,
    intro: str,
    descriptions: dict[str, str],
    rng: SupportsRandint | None = None,
) -> dict[str, Any]:
    """An authored encounter with one or more named enemies and target selection."""
    if not party:
        raise ValueError("At least one playing character is needed for the encounter.")
    if not enemies:
        raise ValueError("An encounter needs at least one enemy.")
    fighters: dict[str, Any] = {
        user_id: _player_fighter(user_id, character_id, sheet, rng)
        for user_id, character_id, sheet in party
    }
    for enemy in enemies:
        if enemy.key in fighters:
            raise ValueError(f"Duplicate combatant key: {enemy.key}")
        fighters[enemy.key] = _enemy_fighter(enemy, rng)
    return _assemble(
        fighters, intro=intro, descriptions=descriptions, labels=_BATTLE_LABELS, rng=rng
    )


def _is_enemy(fighter: dict) -> bool:
    return fighter["user_id"] is None


def _active(fighter: dict) -> bool:
    return fighter["hp"] > 0 and not fighter["withdrawn"]


def _side(encounter: dict, *, enemy: bool) -> list[str]:
    fighters = encounter["fighters"]
    return [
        key
        for key in encounter["order"]
        if _is_enemy(fighters[key]) == enemy and _active(fighters[key])
    ]


def enemy_targets(encounter: dict) -> list[str]:
    """Active enemy keys a player may strike."""
    return _side(encounter, enemy=True)


def current_actor(encounter: dict) -> str | None:
    return None if encounter["outcome"] else encounter["order"][encounter["index"]]


def _finish(encounter: dict, reason: str) -> None:
    descriptions = encounter.get("descriptions", _SPARRING_DESCRIPTIONS)
    encounter["outcome"] = dict(reason=reason, body=descriptions[reason])
    encounter["messages"].append(encounter["outcome"]["body"])


def _advance(encounter: dict) -> None:
    encounter["index"] = (encounter["index"] + 1) % len(encounter["order"])
    if encounter["index"] == 0:
        encounter["round"] += 1


def _attack(encounter: dict, attacker_id: str, target_id: str, rng: SupportsRandint | None) -> None:
    attacker = encounter["fighters"][attacker_id]
    target = encounter["fighters"][target_id]
    result = attack_roll(attacker["bonus"], target["ac"], disadvantage=target["dodging"], rng=rng)
    faces = "/".join(map(str, result.roll.dice + result.roll.dropped))
    line = (
        f"{attacker['name']} attacks {target['name']}: d20 {faces} "
        f"{attacker['bonus']:+} = {result.total} against AC {target['ac']}."
    )
    if target["dodging"]:
        line += " Dodge gives the attack disadvantage (keep the lower die)."
    if result.is_hit:
        damage = roll_damage(attacker["damage"], critical=result.is_critical, rng=rng)
        combatant = Combatant(
            target["name"],
            target["max_hp"],
            current_hp=target["hp"],
            resistances=frozenset(target["resistances"]),
            immunities=frozenset(target["immunities"]),
            vulnerabilities=frozenset(target["vulnerabilities"]),
        )
        combatant.take_damage(damage.total, "bludgeoning")
        lost = target["hp"] - combatant.current_hp
        target["hp"] = combatant.current_hp
        labels = encounter.get("labels", _SPARRING_LABELS)
        line += f" {'Critical hit! ' if result.is_critical else 'Hit. '}{lost} {labels['hp']} lost."
        if target["hp"] == 0:
            line += f" {target['name']} {labels['down']}."
    else:
        line += " Miss."
    encounter["messages"].append(line)


def _settle(encounter: dict, rng: SupportsRandint | None) -> None:
    """Resolve automatic enemy turns and skip inactive fighters, stopping at a human turn."""
    while not encounter["outcome"]:
        if not _side(encounter, enemy=True):
            _finish(encounter, "victory")
        elif not _side(encounter, enemy=False):
            reason = (
                "withdrawn"
                if any(
                    not _is_enemy(f) and f["withdrawn"] for f in encounter["fighters"].values()
                )
                else "defeat"
            )
            _finish(encounter, reason)
        elif encounter["round"] > MAX_ROUNDS:
            _finish(encounter, "limit")
        else:
            key = current_actor(encounter)
            assert key is not None
            fighter = encounter["fighters"][key]
            if not _active(fighter):
                _advance(encounter)
            elif _is_enemy(fighter):
                # Rotate targets by round so one character does not absorb every attack.
                players = _side(encounter, enemy=False)
                target = players[(encounter["round"] - 1) % len(players)]
                _attack(encounter, key, target, rng)
                _advance(encounter)
            else:
                fighter["dodging"] = False  # lasts until the next turn starts
                return


def take_action(
    encounter: dict,
    user_id: str,
    action: str,
    *,
    target: str | None = None,
    rng: SupportsRandint | None = None,
) -> None:
    if encounter["outcome"] or current_actor(encounter) != user_id:
        raise ValueError("Wait for your character's turn.")
    if action not in {"strike", "dodge", "withdraw"}:
        raise ValueError("Choose strike, dodge, or withdraw.")
    encounter["messages"] = []
    actor = encounter["fighters"][user_id]
    if action == "strike":
        targets = enemy_targets(encounter)
        if target is None:
            if len(targets) != 1:
                raise ValueError("Choose which enemy to strike.")
            target = targets[0]
        elif target not in targets:
            raise ValueError("Choose a valid enemy to strike.")
        _attack(encounter, user_id, target, rng)
    elif action == "dodge":
        actor["dodging"] = True
        encounter["messages"].append(f"{actor['name']} dodges until their next turn.")
    else:
        actor["withdrawn"] = True
        labels = encounter.get("labels", _SPARRING_LABELS)
        suffix = " from practice" if labels["stop"] == "practice bout" else ""
        encounter["messages"].append(f"{actor['name']} safely withdraws{suffix}.")
    _advance(encounter)
    _settle(encounter, rng)


def stop_encounter(encounter: dict) -> None:
    if encounter["outcome"]:
        raise ValueError("This encounter has already ended.")
    labels = encounter.get("labels", _SPARRING_LABELS)
    encounter["messages"] = [f"The host stops the {labels['stop']} for the party."]
    _finish(encounter, "withdrawn")
