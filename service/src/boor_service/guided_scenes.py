"""Version-five guided adventure as a data-driven scene graph.

The v1-v4 flow is a hand-written phase machine in ``guided.py``; those runs keep
using it untouched. A v5 run instead walks a declarative graph of scenes here. The
shared infrastructure (session lock, membership, idempotency receipt, revision
check, event append + broadcast) and the lobby all live in ``guided.py`` and serve
every version. This module owns only the *content* actions once the adventure has
begun: choosing an approach, rolling, talking to Mara, fighting, and the wrap-up.

Adding a scene is authoring: define a scene and point a transition at it. No new
phase enum and no version guard. Each scene projects into the same client-facing
fields the panels already read (``pending``, ``result``, ``conversation``,
``encounter``) plus ``scene``/``scene_title``/``scene_intro``/``goal``/``actions``/
``recap`` so the web client can render generically.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service import guided_combat
from boor_service.character import Character as Sheet
from boor_service.db.models import Character
from boor_service.guided_story import (
    CHOICES,
    QUESTIONS,
    answer_question,
    conversation_intro,
    route_ending,
)
from boor_service.mechanics import ability_check

logger = logging.getLogger(__name__)

VERSION = 5

# --- Scene ids --------------------------------------------------------------
CART = "cart"
MARA = "mara"
GATE = "gate"
LANDING = "landing"
BATTLE = "battle"
RECAP = "recap"
FIRST_SCENE = CART


@dataclass(frozen=True)
class Approach:
    id: str
    label: str
    skill: str
    hint: str


@dataclass(frozen=True)
class CheckScene:
    id: str
    title: str
    goal: str
    approaches: tuple[Approach, ...]
    success: str
    failure: str
    next: str
    dc: int = 12
    intro: str = ""
    intro_success: str = ""
    intro_failure: str = ""


CART_INTRO = (
    "On the river road to Emberlow, a delivery cart has slipped into a muddy rut. "
    "Its driver, Mara, holds the reins while the river rises beside the road. "
    "Help her get the cart onto firm ground before the water reaches it."
)

CHECK_SCENES: dict[str, CheckScene] = {
    CART: CheckScene(
        id=CART,
        title="The river-road rescue",
        goal="Get Mara and her cart onto firm ground.",
        intro=CART_INTRO,
        approaches=(
            Approach(
                "lift", "Lift the wheel out of the mud", "athletics", "Uses strength · Athletics"
            ),
            Approach(
                "leverage",
                "Find a firm place to use a branch as a lever",
                "investigation",
                "Uses reasoning · Investigation",
            ),
        ),
        success="The cart rolls onto firm ground. Mara gives you a brass river token in thanks.",
        failure=(
            "The mud gives way. You unload the crates and rescue the cart together, but arrive at "
            "Emberlow after the gate closes. Mara offers shelter at her river camp."
        ),
        next=MARA,
    ),
    GATE: CheckScene(
        id=GATE,
        title="Emberlow's night gate",
        goal="Get your party past the gate guard and into Emberlow.",
        intro_success=(
            "You reach Emberlow beside Mara's cart with time to spare. The gate is closing for the "
            "night, and a tired guard steps into your path."
        ),
        intro_failure=(
            "At dawn you walk with Mara to Emberlow. The gate is open, but the guard is wary of "
            "strangers who arrived with the flood."
        ),
        approaches=(
            Approach(
                "vouch", "Explain that Mara sent you", "persuasion", "Uses charm · Persuasion"
            ),
            Approach(
                "read",
                "Read the guard's mood before you speak",
                "insight",
                "Uses awareness · Insight",
            ),
        ),
        success=(
            "The guard's shoulders ease. 'Any friend of Mara's is welcome. Mind the market square, "
            "though — there's been trouble after dark.'"
        ),
        failure=(
            "The guard waves you to a narrow side gate. You get in, but a pair of toughs loitering "
            "by the market have already marked you as strangers worth following."
        ),
        next=BATTLE,
    ),
    LANDING: CheckScene(
        id=LANDING,
        title="The old ferry landing",
        goal="Find a safe way down to the old ferry landing.",
        intro_success=(
            "With daylight to spare, you leave the road for the high river trail Mara described, "
            "heading for the old ferry landing."
        ),
        intro_failure=(
            "At first light you set out for the high river trail. The delay cost you the morning, "
            "and the flooded bank has narrowed the path to the old ferry landing."
        ),
        approaches=(
            Approach(
                "scout",
                "Scan the trail for a safe path",
                "perception",
                "Uses awareness · Perception",
            ),
            Approach(
                "sneak", "Pick your way quietly along the bank", "stealth", "Uses care · Stealth"
            ),
        ),
        success=(
            "You find dry footing and reach the landing without a sound — until two river bandits "
            "step from the reeds, caught off guard by how ready you are."
        ),
        failure=(
            "Loose stones clatter down the bank ahead of you. Two river bandits already wait "
            "at the landing, and they heard you coming."
        ),
        next=BATTLE,
    ),
}

# Non-lethal outcomes: this introduction excludes permanent character loss.
BATTLE_DESCRIPTIONS = {
    "victory": (
        "The last of them throws down a cudgel and bolts into the dark. You are winded but whole. "
        "No lasting harm comes to anyone in this introduction."
    ),
    "defeat": (
        "It is too much at once — but Mara and a passer-by pull you clear before anyone is badly "
        "hurt. You will remember this fight. No lasting harm comes to anyone in this introduction."
    ),
    "withdrawn": (
        "You break off and slip away into the dark. Living to fight another day is a real choice. "
        "No lasting harm comes to anyone in this introduction."
    ),
    "limit": (
        "A patrol's whistle scatters the fight; everyone melts into the night. "
        "No lasting harm comes to anyone in this introduction."
    ),
}


def _enemies(choice: str, softened: bool) -> list[guided_combat.Enemy]:
    hp = 5 if softened else 8
    if choice == "town":
        pairs = (("tough1", "Market tough"), ("tough2", "Hired bruiser"))
    else:
        pairs = (("bandit1", "River bandit"), ("bandit2", "Reed-cloaked bandit"))
    return [
        guided_combat.Enemy(key, name, hp=hp, ac=12, bonus=3, damage="1d6") for key, name in pairs
    ]


def _battle_intro(choice: str, softened: bool) -> str:
    place = "in Emberlow's market square" if choice == "town" else "at the old ferry landing"
    edge = (
        "You saw them first and set yourselves before they closed."
        if softened
        else "They were ready and waiting, and you had no time to prepare."
    )
    return (
        f"A real fight breaks out {place}. {edge} On your turn, choose an action and a target; "
        "the app rolls the dice and tracks everyone's HP. You can withdraw at any time, and the "
        "host can stop the fight."
    )


# --- Projection helpers -----------------------------------------------------


def _project_check(state: dict, scene: CheckScene, cart_success: bool) -> str:
    if scene.id == CART:
        intro = scene.intro
    else:
        intro = scene.intro_success if cart_success else scene.intro_failure
    state["scene_title"] = scene.title
    state["goal"] = scene.goal
    state["scene_intro"] = intro
    state["actions"] = [
        {"id": a.id, "label": a.label, "skill": a.skill, "hint": a.hint} for a in scene.approaches
    ]
    return intro


def _cart_success(state: dict) -> bool:
    return bool(state.get("scenes", {}).get(CART, {}).get("success"))


# --- Scene entry ------------------------------------------------------------


async def enter_scene(session: AsyncSession, state: dict, scene_id: str, members: list) -> str:
    """Move the run into ``scene_id``, initialising its projected state. Returns narration."""
    state["scene"] = scene_id
    if scene_id in CHECK_SCENES:
        scene = CHECK_SCENES[scene_id]
        state["phase"] = "ready"
        state["pending"] = None
        state["result"] = None
        state["proposal"] = None
        return _project_check(state, scene, _cart_success(state))
    if scene_id == MARA:
        success = _cart_success(state)
        intro = conversation_intro(success)
        state["conversation"] = dict(
            intro=intro,
            questions=[{"id": key, "label": label} for key, label in QUESTIONS.items()],
            choices=[{"id": key, "label": label} for key, label in CHOICES.items()],
            answers=[],
            ending=None,
        )
        state["phase"] = "conversation"
        state["scene_title"] = "A word with Mara"
        state["goal"] = "Learn from Mara, then choose your next destination."
        state["scene_intro"] = intro
        state["actions"] = []
        return intro
    if scene_id == BATTLE:
        choice = state["conversation"]["ending"]["choice"]
        check_scene = GATE if choice == "town" else LANDING
        softened = bool(state.get("scenes", {}).get(check_scene, {}).get("success"))
        party = await _load_party(session, state, members)
        intro = _battle_intro(choice, softened)
        state["encounter"] = guided_combat.start_battle(
            party, _enemies(choice, softened), intro=intro, descriptions=BATTLE_DESCRIPTIONS
        )
        state["phase"] = "combat_outcome" if state["encounter"]["outcome"] else "combat"
        state["scene_title"] = "A fight on the way"
        state["goal"] = "Come through the fight safely."
        state["scene_intro"] = intro
        state["actions"] = []
        return " ".join(state["encounter"]["messages"])
    if scene_id == RECAP:
        state["recap"] = _build_recap(state)
        state["phase"] = "recap"
        state["scene_title"] = "What you did"
        state["goal"] = "Review what changed and where the next session begins."
        state["scene_intro"] = "Here is what your choices added up to."
        state["actions"] = []
        return "The introduction winds down. Review what your choices changed."
    raise HTTPException(409, "Unknown scene.")


async def _load_party(
    session: AsyncSession, state: dict, members: list
) -> list[tuple[str, str, Sheet]]:
    current_members = {str(m.user_id) for m in members}
    party: list[tuple[str, str, Sheet]] = []
    for player_id, participant in state["participants"].items():
        if player_id not in current_members:
            continue
        character = await session.get(Character, uuid.UUID(participant["character_id"]))
        if character is None or str(character.player_id) != player_id:
            raise HTTPException(409, "A character is unavailable. Ask the host to finish here.")
        party.append((player_id, str(character.id), Sheet.from_sheet(character.sheet)))
    if not party:
        raise HTTPException(409, "No playing members remain to continue.")
    return party


def _build_recap(state: dict) -> dict:
    scenes = state.get("scenes", {})
    cart_ok = bool(scenes.get(CART, {}).get("success"))
    lines: list[str] = []
    lines.append(
        "You rescued Mara's cart from the mud and earned a brass river token."
        if cart_ok
        else "You saved Mara's cargo after the cart slipped, and she sheltered you for the night."
    )
    conversation = state.get("conversation") or {}
    ending = conversation.get("ending") or {}
    choice = ending.get("choice")
    if choice == "town":
        check = scenes.get(GATE, {})
        lines.append(
            "At Emberlow's gate you talked your way through and stepped into the town."
            if check.get("success")
            else "The gate guard was uneasy, so you slipped in by a side gate — and drew attention."
        )
    elif choice == "river":
        check = scenes.get(LANDING, {})
        lines.append(
            "You found a quiet path down to the old ferry landing."
            if check.get("success")
            else "The descent to the ferry landing was noisy, costing you the element of surprise."
        )
    reason = scenes.get(BATTLE, {}).get("reason")
    if reason == "victory":
        lines.append("When a fight came, you stood your ground and drove your attackers off.")
    elif reason == "withdrawn":
        lines.append("When a fight came, you chose to break off safely rather than press it.")
    elif reason in {"defeat", "limit"}:
        lines.append("The fight went against you, but you came through it without lasting harm.")
    next_hook = (
        "Your next session begins inside Emberlow, with Mara as a friendly first contact."
        if choice == "town"
        else "Your next session begins at the old ferry landing, with the river road behind you."
    )
    return {"lines": lines, "next": next_hook}


# --- Command application ----------------------------------------------------


async def apply(
    session: AsyncSession, state: dict, body, user, is_host: bool, members: list
) -> str:
    """Apply a v5 content command, mutating ``state`` and returning narration."""
    if body.action in PAUSE_ACTIONS:
        return _apply_pause(state, body, user, is_host)
    if state.get("paused"):
        raise HTTPException(
            409, f"Play is paused by {state['paused']['name']}. Chat is open; resume to continue."
        )
    scene_id = state.get("scene")
    if scene_id in CHECK_SCENES:
        return await _apply_check(session, state, body, user, is_host, members)
    if scene_id == MARA:
        return await _apply_conversation(session, state, body, user, is_host, members)
    if scene_id == BATTLE:
        return await _apply_battle(session, state, body, user, is_host, members)
    if scene_id == RECAP:
        return _apply_recap(state, body, is_host)
    raise HTTPException(409, "Finish the current step before continuing.")


PAUSE_ACTIONS = {"pause", "pause_note", "resume"}
V5_ONLY_ACTIONS = PAUSE_ACTIONS | {"propose", "accept_proposal", "decline_proposal"}


def _apply_pause(state: dict, body, user, is_host: bool) -> str:
    """Any participant pauses instantly; only the pauser or the host resumes.

    The pause takes effect before any explanation is collected: the note is a
    separate, optional follow-up from the pauser. The scene state underneath
    (pending rolls, open proposals, combat turns) is held, not discarded.
    """
    uid = str(user.id)
    paused = state.get("paused")
    if body.action == "pause":
        if uid not in state["seats"]:
            raise HTTPException(403, "Only people at this table can pause play.")
        if not state.get("scene") or state["phase"] == "complete":
            raise HTTPException(409, "There is no play to pause right now.")
        if paused:
            raise HTTPException(409, f"Play is already paused by {paused['name']}.")
        name = state["seats"][uid]["player_name"]
        state["paused"] = {"user_id": uid, "name": name, "note": None}
        logger.info("guided pause by %s at scene=%s phase=%s", uid, state["scene"], state["phase"])
        return f"{name} paused play. Game actions wait until play resumes; chat stays open."
    if not paused:
        raise HTTPException(409, "Play is not paused.")
    if body.action == "pause_note":
        if paused["user_id"] != uid:
            raise HTTPException(403, "Only the person who paused can add a note.")
        note = (body.text or "").strip()
        if not note:
            raise HTTPException(422, "The note is empty. Write a few words, or skip the note.")
        paused["note"] = note
        return f"{paused['name']} added a note to the pause: “{note}”"
    if paused["user_id"] != uid and not is_host:
        raise HTTPException(403, f"Only {paused['name']} or the host can resume play.")
    state["paused"] = None
    logger.info("guided resume by %s (paused by %s)", uid, paused["user_id"])
    resumer = state["seats"].get(uid, {}).get("player_name", "The host")
    return f"{resumer} resumed play."


async def accept_proposal(
    session: AsyncSession, state: dict, approach_id: str | None, *, by: str
) -> str:
    """Run the open proposal as an authored approach; the proposer becomes the roller.

    Shared by the host's "Run as" control and the AI guide. Raises before mutating.
    """
    scene = CHECK_SCENES[state["scene"]]
    participants = state["participants"]
    proposal = state.get("proposal")
    if not proposal or state["phase"] != "ready":
        raise HTTPException(409, "There is no proposal to accept right now.")
    approach = next((a for a in scene.approaches if a.id == approach_id), None)
    if approach is None:
        raise HTTPException(422, "Choose which offered action best fits the proposal.")
    proposer = proposal["user_id"]
    if proposer not in participants:
        raise HTTPException(409, "The player who proposed is no longer in the party.")
    character = await session.get(Character, uuid.UUID(participants[proposer]["character_id"]))
    if character is None or str(character.player_id) != proposer:
        raise HTTPException(409, "That character is unavailable. Ask them to choose again.")
    bonus = Sheet.from_sheet(character.sheet).skill_bonus(approach.skill)
    state["pending"] = dict(
        user_id=proposer,
        character_id=str(character.id),
        name=character.name,
        approach=approach.id,
        label=approach.label,
        skill=approach.skill,
        bonus=bonus,
        dc=scene.dc,
    )
    state["phase"] = "check"
    state["proposal"] = None
    return (
        f"{by} takes {character.name}'s idea (“{proposal['text']}”) as {approach.label}. "
        f"Roll a twenty-sided die; the app adds {bonus:+}."
    )


def decline_proposal(state: dict, reason: str | None, *, by: str) -> str:
    """Decline the open proposal with a written reason. Raises before mutating."""
    proposal = state.get("proposal")
    if not proposal or state["phase"] != "ready":
        raise HTTPException(409, "There is no proposal to respond to right now.")
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(422, "Give a short reason so the player knows what to do next.")
    state["proposal"] = None
    return (
        f"{by} responds to {proposal['name']}'s idea (“{proposal['text']}”): {reason} "
        "Choose one of the offered actions to continue."
    )


async def _apply_check(session, state: dict, body, user, is_host, members) -> str:
    scene = CHECK_SCENES[state["scene"]]
    uid = str(user.id)
    participants = state["participants"]
    if body.action == "propose":
        if state["phase"] != "ready" or uid not in participants:
            raise HTTPException(409, "You can propose an action when it is time to choose one.")
        if state.get("proposal"):
            raise HTTPException(409, "A proposal is already with the host. Wait for their reply.")
        text = (body.text or "").strip()
        if not text:
            raise HTTPException(422, "Describe what you want to try.")
        character = await session.get(Character, uuid.UUID(participants[uid]["character_id"]))
        if character is None or character.player_id != user.id:
            raise HTTPException(403, "You no longer control this character.")
        state["proposal"] = {"user_id": uid, "name": character.name, "text": text}
        return f"{character.name} proposes: “{text}” — waiting for the host to respond."
    if body.action == "accept_proposal":
        if not is_host:
            raise HTTPException(403, "Only the host can respond to a proposal.")
        return await accept_proposal(session, state, body.approach, by="The host")
    if body.action == "decline_proposal":
        if not is_host:
            raise HTTPException(403, "Only the host can respond to a proposal.")
        return decline_proposal(state, body.text, by="The host")
    if body.action == "approach":
        if state["phase"] != "ready" or uid not in participants:
            raise HTTPException(409, "Choose your character and wait for an open action.")
        if state.get("proposal"):
            raise HTTPException(409, "The host is responding to a proposal. Wait for their reply.")
        approach = next((a for a in scene.approaches if a.id == body.approach), None)
        if approach is None:
            raise HTTPException(422, "Choose one of the offered approaches.")
        character = await session.get(Character, uuid.UUID(participants[uid]["character_id"]))
        if character is None or character.player_id != user.id:
            raise HTTPException(403, "You no longer control this character.")
        bonus = Sheet.from_sheet(character.sheet).skill_bonus(approach.skill)
        state["pending"] = dict(
            user_id=uid,
            character_id=str(character.id),
            name=character.name,
            approach=approach.id,
            label=approach.label,
            skill=approach.skill,
            bonus=bonus,
            dc=scene.dc,
        )
        state["phase"] = "check"
        return (
            f"{character.name}: {approach.label}. Roll a twenty-sided die; the app adds {bonus:+}."
        )
    if body.action == "roll":
        pending = state["pending"]
        if state["phase"] != "check" or not pending:
            raise HTTPException(409, "There is no check waiting for a roll.")
        if pending["user_id"] != uid:
            raise HTTPException(403, "This roll belongs to another player.")
        check = ability_check(pending["bonus"], dc=pending["dc"])
        outcome = scene.success if check.is_success else scene.failure
        state["result"] = dict(
            total=check.total,
            die=check.total - pending["bonus"],
            bonus=pending["bonus"],
            dc=pending["dc"],
            success=check.is_success,
            outcome=outcome,
        )
        state.setdefault("scenes", {})[scene.id] = {
            "success": check.is_success,
            "result": state["result"],
        }
        state["phase"] = "outcome"
        state["pending"] = None
        return f"{pending['name']} rolls {check.total} against {pending['dc']}. {outcome}"
    if body.action == "cancel":
        if not is_host or state["phase"] != "check":
            raise HTTPException(403, "Only the host can release a pending check.")
        state.update(phase="ready", pending=None)
        return "The host opens the action again. Anyone with a character may take the lead."
    if body.action == "continue":
        if not is_host:
            raise HTTPException(403, "The host continues after everyone has read the outcome.")
        if state["phase"] != "outcome":
            raise HTTPException(409, "Finish the current check before continuing.")
        return await enter_scene(session, state, scene.next, members)
    raise HTTPException(409, "That action is not available in this scene.")


async def _apply_conversation(session, state: dict, body, user, is_host, members) -> str:
    uid = str(user.id)
    participants = state["participants"]
    if body.action in {"ask", "choose"}:
        if state["phase"] != "conversation":
            raise HTTPException(409, "There is no conversation waiting for an action.")
        if uid not in participants:
            raise HTTPException(403, "Only a playing character can speak for the party.")
        character = await session.get(Character, uuid.UUID(participants[uid]["character_id"]))
        if character is None or character.player_id != user.id:
            raise HTTPException(403, "You no longer control this character.")
        conversation = state["conversation"]
        success = _cart_success(state)
        if body.action == "ask":
            if body.topic is None:
                raise HTTPException(422, "Choose a question to ask Mara.")
            if any(answer["topic"] == body.topic for answer in conversation["answers"]):
                raise HTTPException(409, "Mara has already answered that question for the party.")
            reply = answer_question(body.topic, success)
            conversation["answers"].append(
                dict(
                    topic=body.topic,
                    question=QUESTIONS[body.topic],
                    reply=reply,
                    speaker=character.name,
                    user_id=uid,
                )
            )
            return f"{character.name}: {QUESTIONS[body.topic]} Mara: {reply}"
        if body.choice is None:
            raise HTTPException(422, "Choose where the party will go next.")
        if not conversation["answers"]:
            raise HTTPException(409, "Ask Mara a question before choosing your next stop.")
        ending = route_ending(body.choice, success)
        conversation["ending"] = dict(
            choice=body.choice,
            label=CHOICES[body.choice],
            body=ending,
            speaker=character.name,
            user_id=uid,
        )
        state["phase"] = "decision"
        return f"{character.name} chooses for the party: {CHOICES[body.choice]}. {ending}"
    if body.action == "continue":
        if not is_host:
            raise HTTPException(403, "The host continues after everyone has read the outcome.")
        if state["phase"] != "decision":
            raise HTTPException(409, "Choose the party's destination before continuing.")
        choice = state["conversation"]["ending"]["choice"]
        return await enter_scene(session, state, GATE if choice == "town" else LANDING, members)
    raise HTTPException(409, "That action is not available in this scene.")


async def _apply_battle(session, state: dict, body, user, is_host, members) -> str:
    uid = str(user.id)
    encounter = state.get("encounter")
    if body.action in {"combat_action", "stop_practice"}:
        if state["phase"] != "combat" or not encounter:
            raise HTTPException(409, "There is no active fight.")
        if body.action == "stop_practice":
            if not is_host:
                raise HTTPException(403, "Only the host can stop the fight for everyone.")
            guided_combat.stop_encounter(encounter)
        else:
            if body.move is None:
                raise HTTPException(422, "Choose a combat action.")
            if guided_combat.current_actor(encounter) != uid:
                raise HTTPException(403, "Wait for your character's turn.")
            fighter = encounter["fighters"].get(uid)
            if fighter is None:
                raise HTTPException(403, "You are not in this fight.")
            character = await session.get(Character, uuid.UUID(fighter["character_id"]))
            if character is None or character.player_id != user.id:
                raise HTTPException(403, "You no longer control this character.")
            try:
                guided_combat.take_action(encounter, uid, body.move, target=body.target)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
        if encounter["outcome"]:
            state["phase"] = "combat_outcome"
            state.setdefault("scenes", {})[BATTLE] = {"reason": encounter["outcome"]["reason"]}
        return " ".join(encounter["messages"])
    if body.action == "continue":
        if not is_host:
            raise HTTPException(403, "The host continues after everyone has read the outcome.")
        if state["phase"] != "combat_outcome":
            raise HTTPException(409, "Finish the fight before continuing.")
        return await enter_scene(session, state, RECAP, members)
    raise HTTPException(409, "That action is not available in this scene.")


def _apply_recap(state: dict, body, is_host: bool) -> str:
    if body.action != "continue":
        raise HTTPException(409, "That action is not available in this scene.")
    if not is_host:
        raise HTTPException(403, "The host finishes after everyone has read the recap.")
    if state["phase"] != "recap":
        raise HTTPException(409, "Finish the recap before continuing.")
    state["phase"] = "complete"
    return (
        "Introduction complete. You made checks, spoke in character, chose a path, and came "
        "through a real fight. That is the rhythm of a session."
    )
