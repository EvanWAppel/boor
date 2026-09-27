"""Versioned, authored tutorial. Public snapshots and command receipts live in the log.

The game-session row serializes commands, session ending, and event appends. A
snapshot is accepted only from a server-authored narration event; chat payloads
are never game state. No model or client-supplied dice values drive this flow.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service import realtime
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
from boor_service.mechanics import ability_check

router = APIRouter()
TYPE = "guided_cart_v1"
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
    action: Literal["start", "select", "approach", "roll", "cancel", "continue"]
    character_id: uuid.UUID | None = None
    pregen: Literal["guardian", "scholar"] | None = None
    approach: Literal["lift", "leverage"] | None = None


def events_query(session_id: uuid.UUID):
    return select(SessionEvent).where(
        SessionEvent.session_id == session_id,
        SessionEvent.kind == EventKind.narration,
        SessionEvent.payload["type"].astext == TYPE,
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
        if receipt.payload["command"] != body.model_dump(mode="json"):
            raise HTTPException(409, "This request ID was already used for a different action.")
        return {"state": await latest_state(session, game_session.id)}
    state: dict[str, Any] | None = await latest_state(session, game_session.id)
    if body.revision != (state["revision"] if state else 0):
        raise HTTPException(409, "The table has moved on. Review the current step and try again.")
    uid = str(user.id)
    if body.action == "start":
        if not is_host:
            raise HTTPException(403, "Only the host can start the tutorial.")
        if state:
            raise HTTPException(
                409, "This tutorial has already started. Open a new session to replay."
            )
        initial: dict[str, Any] = dict(
            version=1,
            revision=0,
            phase="ready",
            participants={},
            pending=None,
            result=None,
            intro=INTRO,
        )
        state = initial
        narration = INTRO
    else:
        if state is None:
            raise HTTPException(409, "Ask the host to start the tutorial first.")
        participants = state["participants"]
        if body.action == "select":
            if state["phase"] != "ready":
                raise HTTPException(409, "Character selection is closed while a check is underway.")
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
                # One starter per person per run, even if a fresh command ID is submitted.
                if uid in participants:
                    raise HTTPException(409, "You already chose a character for this tutorial.")
                assert body.pregen is not None
                sheet = PREGENS[body.pregen]
                character = Character(
                    campaign_id=game_session.campaign_id,
                    player_id=user.id,
                    name=sheet.name,
                    level=sheet.level,
                    sheet=sheet.to_sheet(),
                )
                session.add(character)
                await session.flush()
            participants[uid] = {"character_id": str(character.id), "name": character.name}
            narration = f"{user.display_name or 'A player'} joins the rescue as {character.name}."
        elif body.action == "approach":
            if state["phase"] != "ready" or uid not in participants:
                raise HTTPException(409, "Choose your character and wait for an open action.")
            if body.approach is None:
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
            if state["phase"] != "outcome":
                raise HTTPException(409, "Resolve the check first.")
            state["phase"] = "complete"
            narration = (
                "Cart rescue complete. You chose an approach, made a check, and changed the story."
            )
    state["revision"] += 1
    event = await repository.append_event(
        session,
        game_session=game_session,
        kind=EventKind.narration,
        actor=user,
        actor_label="Guide",
        body=narration,
        payload={
            "type": TYPE,
            "state": state,
            "request_id": str(body.request_id),
            "command": body.model_dump(mode="json"),
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
            "display_name": "Guide",
            "audience": "table",
        },
    )
    return {"state": state}
