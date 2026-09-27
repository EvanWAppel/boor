"""Bounded sparring lesson; pure snapshot transitions over the existing rules engine.

Practice HP is scoped to this encounter, never written into character sheets.
Randomness is injectable for deterministic turn/attack/defense tests.
"""

from __future__ import annotations

from typing import Any

from boor_service.character import Character
from boor_service.combat import Combatant
from boor_service.dice import SupportsRandint, roll_d20
from boor_service.mechanics import attack_roll, roll_damage

MAX_ROUNDS = 5
MARA = "mara"


def start_encounter(
    party: list[tuple[str, str, Character]],
    route: str,
    *,
    rng: SupportsRandint | None = None,
) -> dict[str, Any]:
    if not party:
        raise ValueError("At least one playing character is needed for practice.")
    fighters: dict[str, Any] = {}
    for user_id, character_id, sheet in party:
        modifier = max(sheet.ability_modifier("str"), sheet.ability_modifier("dex"))
        fighters[user_id] = dict(
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
    fighters[MARA] = dict(
        name="Mara",
        user_id=None,
        hp=8 + 4 * len(party),
        max_hp=8 + 4 * len(party),
        ac=12,
        bonus=3,
        damage="1d4+1",
        initiative=roll_d20(1, rng=rng).total,
        dodging=False,
        withdrawn=False,
        resistances=[],
        immunities=[],
        vulnerabilities=[],
    )
    order = sorted(fighters, key=lambda key: (-fighters[key]["initiative"], key))
    location = (
        "In a quiet yard in Emberlow" if route == "town" else "Before you take the river trail"
    )
    encounter: dict[str, Any] = dict(
        intro=f"{location}, Mara offers a short sparring lesson with padded practice staffs. "
        "Take turns, watch your practice HP, and stop whenever you like.",
        fighters=fighters,
        order=order,
        index=0,
        round=1,
        max_rounds=MAX_ROUNDS,
        outcome=None,
        messages=[],
    )
    encounter["messages"] = [encounter["intro"], "Initiative rolls set the turn order."]
    _settle(encounter, rng)
    return encounter


def _active(fighter: dict) -> bool:
    return fighter["hp"] > 0 and not fighter["withdrawn"]


def current_actor(encounter: dict) -> str | None:
    return None if encounter["outcome"] else encounter["order"][encounter["index"]]


def _finish(encounter: dict, reason: str) -> None:
    descriptions = {
        "victory": "Mara yields with a grin. Your party won the practice bout.",
        "defeat": "Mara lowers her staff and helps you up. The lesson ends safely.",
        "withdrawn": "Your party stops the practice bout. Stepping away is a useful choice.",
        "limit": "Mara calls time after five rounds. You have practiced taking turns.",
    }
    encounter["outcome"] = dict(
        reason=reason,
        body=descriptions[reason]
        + " Everyone recovers after practice; your character sheets are unchanged.",
    )
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
        line += f" {'Critical hit! ' if result.is_critical else 'Hit. '}{lost} practice HP lost."
        if target["hp"] == 0:
            line += f" {target['name']} sits out the rest of the bout."
    else:
        line += " Miss."
    encounter["messages"].append(line)


def _settle(encounter: dict, rng: SupportsRandint | None) -> None:
    """Resolve automatic turns and skip inactive fighters, stopping at a human turn."""
    while not encounter["outcome"]:
        fighters = encounter["fighters"]
        party = [key for key in encounter["order"] if key != MARA and _active(fighters[key])]
        if fighters[MARA]["hp"] == 0:
            _finish(encounter, "victory")
        elif not party:
            reason = (
                "withdrawn"
                if any(f["withdrawn"] for k, f in fighters.items() if k != MARA)
                else "defeat"
            )
            _finish(encounter, reason)
        elif encounter["round"] > MAX_ROUNDS:
            _finish(encounter, "limit")
        else:
            key = current_actor(encounter)
            if key == MARA:
                # Rotate targets by round so one character does not absorb every attack.
                target = party[(encounter["round"] - 1) % len(party)]
                _attack(encounter, MARA, target, rng)
                _advance(encounter)
            elif key is not None and not _active(fighters[key]):
                _advance(encounter)
            else:
                assert key is not None
                fighters[key]["dodging"] = False  # lasts until the next turn starts
                return


def take_action(
    encounter: dict,
    user_id: str,
    action: str,
    *,
    rng: SupportsRandint | None = None,
) -> None:
    if encounter["outcome"] or current_actor(encounter) != user_id or user_id == MARA:
        raise ValueError("Wait for your character's turn.")
    if action not in {"strike", "dodge", "withdraw"}:
        raise ValueError("Choose strike, dodge, or withdraw.")
    encounter["messages"] = []
    actor = encounter["fighters"][user_id]
    if action == "strike":
        _attack(encounter, user_id, MARA, rng)
    elif action == "dodge":
        actor["dodging"] = True
        encounter["messages"].append(f"{actor['name']} dodges until their next turn.")
    else:
        actor["withdrawn"] = True
        encounter["messages"].append(f"{actor['name']} safely withdraws from practice.")
    _advance(encounter)
    _settle(encounter, rng)


def stop_encounter(encounter: dict) -> None:
    if encounter["outcome"]:
        raise ValueError("Practice has already ended.")
    encounter["messages"] = ["The host stops the practice bout for the party."]
    _finish(encounter, "withdrawn")
