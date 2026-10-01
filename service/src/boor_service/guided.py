"""Versioned, authored tutorial. Public snapshots and command receipts live in the log.

The game-session row serializes commands, session ending, and event appends. A
snapshot is accepted only from a server-authored narration event; chat payloads
are never game state. No model or client-supplied dice values drive this flow; the
optional AI guide (``guided_ai``) only chooses among authored approaches.
"""

from __future__ import annotations

import copy
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from boor_service import guided_ai, guided_combat, guided_scenes, realtime
from boor_service.auth.dependencies import CurrentUser, GameSessionForMember, SessionDep
from boor_service.character import Character as Sheet
from boor_service.db import repository
from boor_service.db.models import (
    Character,
    EventKind,
    GameSession,
    MembershipRole,
    SessionEvent,
    SessionStatus,
)
from boor_service.db.session import get_sessionmaker
from boor_service.guided_story import (
    CHOICES,
    QUESTIONS,
    answer_question,
    conversation_intro,
    route_ending,
)
from boor_service.mechanics import ability_check

router = APIRouter()
TYPE = "guided_cart_v5"
EVENT_TYPES = {
    1: "guided_cart_v1",
    2: "guided_cart_v2",
    3: "guided_cart_v3",
    4: "guided_cart_v4",
    5: TYPE,
}
INTRO = (
    "On the river road to Emberlow, a delivery cart has slipped into a muddy rut. "
    "Its driver, Mara, holds the reins while the river rises beside the road. "
    "Help her get the cart onto firm ground before the water reaches it."
)
APPROACHES = {
    "lift": ("Lift the wheel out of the mud", "athletics"),
    "leverage": ("Find a firm place to use a branch as a lever", "investigation"),
}
PREGENS = {
    "guardian": Sheet(
        "Rowan",
        1,
        dict(str=16, dex=12, con=14, int=10, wis=13, cha=8),
        12,
        skill_proficiencies=frozenset({"athletics", "perception"}),
    ),
    "scholar": Sheet(
        "Wren",
        1,
        dict(str=8, dex=14, con=12, int=16, wis=13, cha=10),
        8,
        skill_proficiencies=frozenset({"investigation", "arcana"}),
    ),
}


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: uuid.UUID
    revision: int = Field(ge=0)
    action: Literal[
        "start",
        "select",
        "approach",
        "roll",
        "cancel",
        "continue",
        "ready",
        "unready",
        "watch",
        "join",
        "exclude",
        "begin",
        "ask",
        "choose",
        "combat_action",
        "stop_practice",
        "skip_practice",
        "propose",
        "accept_proposal",
        "decline_proposal",
        "pause",
        "pause_note",
        "resume",
    ]
    move: Literal["strike", "dodge", "withdraw"] | None = None
    topic: Literal["road", "river", "mara"] | None = None
    choice: Literal["town", "river"] | None = None
    target_user_id: uuid.UUID | None = None
    character_id: uuid.UUID | None = None
    pregen: Literal["guardian", "scholar"] | None = None
    # Widened for v5 authored scenes (each scene validates its own approach ids);
    # the v1-v4 path still checks membership in APPROACHES before use.
    approach: str | None = None
    # Combat target key (an enemy fighter id) for v5 encounters with more than one foe.
    target: str | None = None
    # Free-form proposal text (v5 "try something else"), a host's decline reason,
    # or the pauser's optional note.
    text: str | None = Field(default=None, max_length=500)


def events_query(session_id: uuid.UUID):
    return select(SessionEvent).where(
        SessionEvent.session_id == session_id,
        SessionEvent.kind == EventKind.narration,
        SessionEvent.payload["type"].astext.in_(EVENT_TYPES.values()),
        SessionEvent.ai_generated.is_(False),
    )


async def latest_state(db: AsyncSession, session_id: uuid.UUID) -> dict[str, Any] | None:
    event = await db.scalar(events_query(session_id).order_by(SessionEvent.seq.desc()).limit(1))
    return copy.deepcopy(event.payload["state"]) if event else None


@router.get("/sessions/{session_id}/guided")
async def read_guided(game_session: GameSessionForMember, session: SessionDep) -> dict:
    return {"state": await latest_state(session, game_session.id), "status": game_session.status}


@router.post("/sessions/{session_id}/guided")
async def command_guided(
    body: Command,
    game_session: GameSessionForMember,
    user: CurrentUser,
    session: SessionDep,
    background: BackgroundTasks,
    sessions: Annotated[async_sessionmaker, Depends(get_sessionmaker)],
) -> dict:
    await session.execute(
        select(GameSession.id).where(GameSession.id == game_session.id).with_for_update()
    )
    await session.refresh(game_session)
    # Ended sessions are read-only, including retries of previously accepted commands.
    if game_session.status != SessionStatus.active:
        raise HTTPException(409, "This session has ended or is not active.")
    members = await repository.campaign_members(session, campaign_id=game_session.campaign_id)
    member = next((m for m in members if m.user_id == user.id), None)
    if member is None:
        raise HTTPException(403, "You are no longer a member of this campaign.")
    is_host = member.role == MembershipRole.dm
    receipt = await session.scalar(
        events_query(game_session.id).where(
            SessionEvent.payload["request_id"].astext == str(body.request_id),
            SessionEvent.actor_user_id == user.id,
        )
    )
    if receipt:
        if {k: v for k, v in receipt.payload["command"].items() if v is not None} != (
            body.model_dump(mode="json", exclude_none=True)
        ):
            raise HTTPException(409, "This request ID was already used for a different action.")
        return {"state": await latest_state(session, game_session.id)}
    state: dict[str, Any] | None = await latest_state(session, game_session.id)
    if body.revision != (state["revision"] if state else 0):
        raise HTTPException(409, "The table has moved on. Review the current step and try again.")
    uid = str(user.id)
    if body.action == "propose" and state and (wait := guided_ai.cooldown_remaining(state)):
        raise HTTPException(429, f"The AI guide needs a moment. Try again in {wait} seconds.")
    if body.action == "start":
        if not is_host:
            raise HTTPException(403, "Only the host can start the tutorial.")
        if state:
            raise HTTPException(
                409, "This tutorial has already started. Open a new session to replay."
            )
        initial: dict[str, Any] = dict(
            version=guided_scenes.VERSION,
            encounter=None,
            practice_skipped=False,
            conversation=None,
            revision=0,
            phase="lobby",
            participants={},
            starters={},
            seats={
                str(m.user_id): {
                    "player_name": m.user.display_name or "Player",
                    "ready": False,
                    "watching": False,
                }
                for m in members
            },
            pending=None,
            result=None,
            intro=INTRO,
            # v5 scene-graph fields; populated once the host begins the adventure.
            scene=None,
            scenes={},
            recap=None,
            scene_title=None,
            scene_intro=None,
            goal=None,
            actions=[],
            proposal=None,
            paused=None,
        )
        state = initial
        narration = (
            "The lobby is open. Choose a character or watch, then tell the host you are ready."
        )
    else:
        if state is None:
            raise HTTPException(409, "Ask the host to start the tutorial first.")
        participants = state["participants"]
        lobby_actions = {"ready", "unready", "watch", "join", "exclude", "begin"}
        if body.action in lobby_actions:
            if state["phase"] != "lobby":
                raise HTTPException(409, "The lobby is closed. Join the next session to play.")
            seats = state["seats"]
            if body.action == "join":
                if uid in seats:
                    raise HTTPException(409, "You already have a place in this lobby.")
                seats[uid] = dict(
                    player_name=user.display_name or "Player", ready=False, watching=False
                )
                narration = f"{seats[uid]['player_name']} joins the lobby."
            elif body.action == "exclude":
                if not is_host:
                    raise HTTPException(403, "Only the host can mark a player absent.")
                target = str(body.target_user_id)
                if target == uid or target not in seats:
                    raise HTTPException(409, "Choose another player in this lobby.")
                seat = seats.pop(target)
                participants.pop(target, None)
                narration = f"The host marked {seat['player_name']} absent for this introduction."
            elif body.action == "begin":
                if not is_host:
                    raise HTTPException(403, "Only the host can begin the adventure.")
                if not participants or not all(seat["ready"] for seat in seats.values()):
                    raise HTTPException(
                        409, "Wait for everyone to be ready, with at least one player."
                    )
                member_ids = {str(m.user_id) for m in members}
                if set(seats) - member_ids:
                    raise HTTPException(
                        409, "Mark departed campaign members absent before beginning."
                    )
                for player_id, participant in participants.items():
                    character = await session.get(Character, uuid.UUID(participant["character_id"]))
                    if (
                        character is None
                        or str(character.player_id) != player_id
                        or character.campaign_id != game_session.campaign_id
                    ):
                        raise HTTPException(
                            409, "A selected character is unavailable. Choose again."
                        )
                if state["version"] >= 5:
                    narration = await guided_scenes.enter_scene(
                        session, state, guided_scenes.FIRST_SCENE, members
                    )
                else:
                    state["phase"] = "ready"
                    narration = INTRO
            else:
                if uid not in seats:
                    raise HTTPException(409, "Join the lobby first.")
                if body.action == "watch":
                    participants.pop(uid, None)
                    seats[uid].update(watching=True, ready=True)
                elif body.action == "ready":
                    if uid not in participants and not seats[uid]["watching"]:
                        raise HTTPException(409, "Choose a character or choose to watch first.")
                    seats[uid]["ready"] = True
                else:
                    seats[uid]["ready"] = False
                narration = f"{seats[uid]['player_name']} is " + (
                    "ready to watch."
                    if seats[uid]["ready"] and seats[uid]["watching"]
                    else "ready to play."
                    if seats[uid]["ready"]
                    else "not ready yet."
                )
        elif body.action == "select":
            selection_phase = "lobby" if state["version"] >= 2 else "ready"
            if state["phase"] != selection_phase:
                raise HTTPException(409, "Character selection is closed while a check is underway.")
            if state["version"] >= 2 and uid not in state["seats"]:
                raise HTTPException(409, "Join the lobby first.")
            if bool(body.character_id) == bool(body.pregen):
                raise HTTPException(422, "Choose one of your characters or one starter character.")
            if body.character_id:
                character = await session.get(Character, body.character_id)
                if (
                    character is None
                    or character.campaign_id != game_session.campaign_id
                    or character.player_id != user.id
                ):
                    raise HTTPException(403, "Choose a character you own in this campaign.")
            else:
                # Reuse each starter template per person/run when switching characters.
                if uid in participants and state["version"] == 1:
                    raise HTTPException(409, "You already chose a character for this tutorial.")
                assert body.pregen is not None
                sheet = PREGENS[body.pregen]
                starter_id = state.get("starters", {}).get(uid, {}).get(body.pregen)
                character = (
                    await session.get(Character, uuid.UUID(starter_id)) if starter_id else None
                )
                if character is None:
                    character = Character(
                        campaign_id=game_session.campaign_id,
                        player_id=user.id,
                        name=sheet.name,
                        level=sheet.level,
                        sheet=sheet.to_sheet(),
                    )
                    session.add(character)
                    await session.flush()
                    if state["version"] >= 2:
                        state["starters"].setdefault(uid, {})[body.pregen] = str(character.id)
                elif character.player_id != user.id:
                    raise HTTPException(403, "You no longer control this starter character.")
            participants[uid] = {"character_id": str(character.id), "name": character.name}
            if state["version"] >= 2:
                state["seats"][uid].update(ready=False, watching=False)
            narration = f"{user.display_name or 'A player'} joins the rescue as {character.name}."
        elif state["version"] >= 5:
            # v5 runs walk the data-driven scene graph; v1-v4 keep the branches below.
            narration = await guided_scenes.apply(session, state, body, user, is_host, members)
        elif body.action in guided_scenes.V5_ONLY_ACTIONS:
            # Never let a v5-only action fall through to the legacy "continue" branch.
            raise HTTPException(409, "This action isn't available in this version of the intro.")
        elif body.action == "approach":
            if state["phase"] != "ready" or uid not in participants:
                raise HTTPException(409, "Choose your character and wait for an open action.")
            if body.approach not in APPROACHES:
                raise HTTPException(422, "Choose an approach.")
            character = await session.get(Character, uuid.UUID(participants[uid]["character_id"]))
            if character is None or character.player_id != user.id:
                raise HTTPException(403, "You no longer control this character.")
            label, skill = APPROACHES[body.approach]
            bonus = Sheet.from_sheet(character.sheet).skill_bonus(skill)
            state["pending"] = dict(
                user_id=uid,
                character_id=str(character.id),
                name=character.name,
                approach=body.approach,
                label=label,
                skill=skill,
                bonus=bonus,
                dc=12,
            )
            state["phase"] = "check"
            narration = (
                f"{character.name}: {label}. Roll a twenty-sided die; the app adds {bonus:+}."
            )
        elif body.action == "roll":
            pending = state["pending"]
            if state["phase"] != "check" or not pending:
                raise HTTPException(409, "There is no check waiting for a roll.")
            if pending["user_id"] != uid:
                raise HTTPException(403, "This roll belongs to another player.")
            check = ability_check(pending["bonus"], dc=pending["dc"])
            outcome = (
                "The cart rolls onto firm ground. Mara gives you a brass river token in thanks."
                if check.is_success
                else "The mud gives way. You unload the crates and rescue the cart together, "
                "but arrive at Emberlow after the gate closes. "
                "Mara offers shelter at her river camp."
            )
            state["result"] = dict(
                total=check.total,
                die=check.total - pending["bonus"],
                bonus=pending["bonus"],
                dc=pending["dc"],
                success=check.is_success,
                outcome=outcome,
            )
            state["phase"] = "outcome"
            narration = f"{pending['name']} rolls {check.total} against 12. {outcome}"
            state["pending"] = None
        elif body.action in {"ask", "choose"}:
            if state["phase"] != "conversation" or state["version"] < 3:
                raise HTTPException(409, "There is no conversation waiting for an action.")
            if uid not in participants:
                raise HTTPException(403, "Only a playing character can speak for the party.")
            character = await session.get(Character, uuid.UUID(participants[uid]["character_id"]))
            if character is None or character.player_id != user.id:
                raise HTTPException(403, "You no longer control this character.")
            conversation = state["conversation"]
            success = state["result"]["success"]
            if body.action == "ask":
                if body.topic is None:
                    raise HTTPException(422, "Choose a question to ask Mara.")
                if any(answer["topic"] == body.topic for answer in conversation["answers"]):
                    raise HTTPException(
                        409, "Mara has already answered that question for the party."
                    )
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
                narration = f"{character.name}: {QUESTIONS[body.topic]} Mara: {reply}"
            else:
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
                narration = (
                    f"{character.name} chooses for the party: {CHOICES[body.choice]}. {ending}"
                )
        elif body.action in {"combat_action", "stop_practice", "skip_practice"}:
            if body.action == "skip_practice":
                if not is_host:
                    raise HTTPException(403, "Only the host can skip the practice lesson.")
                if state["version"] < 4 or state["phase"] != "decision":
                    raise HTTPException(409, "Practice can only be skipped before it begins.")
                state.update(phase="complete", practice_skipped=True)
                narration = (
                    "The party finishes the introduction without the optional practice bout."
                )
            else:
                if state["phase"] != "combat" or not state.get("encounter"):
                    raise HTTPException(409, "There is no active practice bout.")
                if body.action == "stop_practice":
                    if not is_host:
                        raise HTTPException(403, "Only the host can stop practice for everyone.")
                    guided_combat.stop_encounter(state["encounter"])
                else:
                    if body.move is None:
                        raise HTTPException(422, "Choose a practice action.")
                    if guided_combat.current_actor(state["encounter"]) != uid:
                        raise HTTPException(403, "Wait for your character's turn.")
                    fighter = state["encounter"]["fighters"][uid]
                    character = await session.get(Character, uuid.UUID(fighter["character_id"]))
                    if character is None or character.player_id != user.id:
                        raise HTTPException(403, "You no longer control this character.")
                    guided_combat.take_action(state["encounter"], uid, body.move)
                if state["encounter"]["outcome"]:
                    state["phase"] = "combat_outcome"
                narration = " ".join(state["encounter"]["messages"])
        elif body.action == "cancel":
            if not is_host or state["phase"] != "check":
                raise HTTPException(403, "Only the host can release a pending check.")
            state.update(phase="ready", pending=None)
            narration = (
                "The host opens the action again. Anyone with a character may take the lead."
            )
        else:
            if not is_host:
                raise HTTPException(403, "The host continues after everyone has read the outcome.")
            if state["phase"] == "outcome" and state["version"] >= 3:
                narration = conversation_intro(state["result"]["success"])
                state["conversation"] = dict(
                    intro=narration,
                    questions=[dict(id=key, label=label) for key, label in QUESTIONS.items()],
                    choices=[dict(id=key, label=label) for key, label in CHOICES.items()],
                    answers=[],
                    ending=None,
                )
                state["phase"] = "conversation"
            elif state["phase"] == "decision" and state["version"] >= 4:
                party = []
                current_members = {str(m.user_id) for m in members}
                for player_id, participant in participants.items():
                    if player_id not in current_members:
                        continue
                    character = await session.get(Character, uuid.UUID(participant["character_id"]))
                    if character is None or str(character.player_id) != player_id:
                        raise HTTPException(
                            409, "A character is unavailable. Finish without practice."
                        )
                    party.append((player_id, str(character.id), Sheet.from_sheet(character.sheet)))
                if not party:
                    raise HTTPException(409, "No playing members remain. Finish without practice.")
                state["encounter"] = guided_combat.start_encounter(
                    party, state["conversation"]["ending"]["choice"]
                )
                state["phase"] = "combat_outcome" if state["encounter"]["outcome"] else "combat"
                narration = " ".join(state["encounter"]["messages"])
            elif state["phase"] == "combat_outcome" and state["version"] >= 4:
                state["phase"] = "complete"
                narration = (
                    "Introduction complete. You made story choices and practiced combat turns."
                )
            elif state["phase"] == "outcome" or (
                state["phase"] == "decision" and state["version"] >= 3
            ):
                state["phase"] = "complete"
                narration = (
                    "Introduction complete. You rescued the cart, spoke with Mara, "
                    "and chose your next destination."
                    if state["version"] >= 3
                    else "Cart rescue complete. You chose an approach, "
                    "made a check, and changed the story."
                )
            else:
                raise HTTPException(409, "Finish the current scene before continuing.")
    ai_client = None
    if body.action == "propose" and state["version"] >= 5 and state.get("proposal"):
        ai_client = guided_ai.get_client()
        if ai_client is not None:
            state["proposal"]["ai"] = "thinking"
            state["ai_last_call"] = guided_ai.now()
    await record_state(
        session,
        game_session,
        state,
        narration,
        actor=user,
        label="Guide",
        request_id=str(body.request_id),
        command=body.model_dump(mode="json"),
    )
    if ai_client is not None:
        # The model call runs after the response, outside this request's DB transaction.
        background.add_task(
            guided_ai.run, sessions, game_session.id, ai_client, copy.deepcopy(state)
        )
    return {"state": state}


async def record_state(
    session: AsyncSession,
    game_session: GameSession,
    state: dict[str, Any],
    narration: str,
    *,
    actor: Any,
    label: str,
    request_id: str,
    command: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> None:
    """Bump the revision, persist the snapshot as a narration event, commit, broadcast.

    The caller must hold the game-session row lock.
    """
    state["revision"] += 1
    event = await repository.append_event(
        session,
        game_session=game_session,
        kind=EventKind.narration,
        actor=actor,
        actor_label=label,
        body=narration,
        payload={
            "type": EVENT_TYPES[state["version"]],
            "state": state,
            "request_id": request_id,
            "command": command,
            **(extra or {}),
        },
    )
    await session.commit()
    await realtime.hub.broadcast(
        game_session.id,
        {
            "type": "event",
            "seq": event.seq,
            "kind": "narration",
            "body": event.body,
            "payload": event.payload,
            "display_name": label,
            "audience": "table",
        },
    )
