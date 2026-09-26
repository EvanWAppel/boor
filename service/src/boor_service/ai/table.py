"""Human-DM-triggered stand-in turns for the single-process session service."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Iterator
from typing import Annotated, cast

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from boor_service import realtime
from boor_service.ai.actions import Disposition, Entity, GameState
from boor_service.ai.standin import (
    DEFAULT_MODEL,
    StandInError,
    SupportsMessages,
    build_standin_context,
    decide_action,
    event_kind_for,
    event_payload,
    scoped_timeline_text,
)
from boor_service.auth.dependencies import (
    CharacterForEditor,
    CurrentUser,
    GameSessionForDM,
    GameSessionForMember,
    SessionDep,
)
from boor_service.db import repository
from boor_service.db.models import Character, EventKind, GameSession, SessionEvent, SessionStatus

router = APIRouter()
logger = logging.getLogger(__name__)
# Same single-process boundary as SessionHub. One model request per session at a time.
_busy: set[uuid.UUID] = set()


def get_standin_client() -> Iterator[SupportsMessages]:
    if os.environ.get("ENABLE_STANDINS") != "1" or not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "AI turns are not enabled on this table yet.")
    with anthropic.Anthropic(timeout=20, max_retries=0) as client:
        yield cast(SupportsMessages, client)


class ControlIn(BaseModel):
    enabled: bool


class TurnIn(BaseModel):
    request_id: uuid.UUID


def frame(event: SessionEvent) -> dict:
    return {
        "type": "event",
        "seq": event.seq,
        "kind": event.kind.value,
        "body": event.body,
        "payload": event.payload,
        "display_name": event.actor_label,
        "ai_generated": event.ai_generated,
        "audience": event.audience.value,
    }


async def control_event(db, game, character_id):
    return await db.scalar(
        select(SessionEvent)
        .where(
            SessionEvent.session_id == game.id,
            SessionEvent.kind == EventKind.system,
            SessionEvent.payload["type"].astext == "standin_control",
            SessionEvent.payload["character_id"].astext == str(character_id),
        )
        .order_by(SessionEvent.seq.desc())
        .limit(1)
    )


@router.put("/sessions/{session_id}/standins/{character_id}")
async def set_control(
    body: ControlIn,
    game_session: GameSessionForMember,
    character: CharacterForEditor,
    user: CurrentUser,
    session: SessionDep,
) -> dict:
    if character.campaign_id != game_session.campaign_id:
        raise HTTPException(404, "Character is not in this campaign.")
    await session.execute(
        select(GameSession.id).where(GameSession.id == game_session.id).with_for_update()
    )
    await session.refresh(game_session)
    if game_session.status != SessionStatus.active:
        raise HTTPException(409, "This session is not active.")
    if body.enabled:
        profile = await repository.personality_profile_for(session, character=character)
        if profile is None or not profile.persona.strip():
            raise HTTPException(409, "Save a personality profile before enabling a stand-in.")
    control_label = "AI stand-in enabled" if body.enabled else "player control restored"
    event = await repository.append_event(
        session,
        game_session=game_session,
        kind=EventKind.system,
        actor=user,
        body=f"{character.name}: {control_label}.",
        payload={
            "type": "standin_control",
            "character_id": str(character.id),
            "enabled": body.enabled,
        },
    )
    await session.commit()
    await realtime.hub.broadcast(game_session.id, frame(event))
    return frame(event)


@router.post("/sessions/{session_id}/standins/{character_id}/turn")
async def take_turn(
    character_id: uuid.UUID,
    body: TurnIn,
    game_session: GameSessionForDM,
    session: SessionDep,
    client: Annotated[SupportsMessages, Depends(get_standin_client)],
) -> dict:
    if game_session.id in _busy:
        raise HTTPException(409, "A stand-in is already thinking for this session.")
    character = await session.get(Character, character_id)
    if character is None or character.campaign_id != game_session.campaign_id:
        raise HTTPException(404, "Character is not in this campaign.")
    previous = await session.scalar(
        select(SessionEvent).where(
            SessionEvent.session_id == game_session.id,
            SessionEvent.ai_generated.is_(True),
            SessionEvent.payload["request_id"].astext == str(body.request_id),
            SessionEvent.payload["character_id"].astext == str(character_id),
        )
    )
    if previous is not None:
        return frame(previous)
    control = await control_event(session, game_session, character_id)
    if game_session.status != SessionStatus.active or not control or not control.payload["enabled"]:
        raise HTTPException(409, "Enable this character's stand-in in an active session first.")
    # Recheck immediately before acquiring: the DB reads above may have yielded.
    if game_session.id in _busy:
        raise HTTPException(409, "A stand-in is already thinking for this session.")
    _busy.add(game_session.id)
    status = {"type": "standin_status", "character_id": str(character_id)}
    try:
        party = await repository.characters_in_campaign(
            session, campaign_id=game_session.campaign_id
        )
        state = GameState(
            actor_id=str(character_id),
            entities={
                str(c.id): Entity(
                    str(c.id),
                    c.name,
                    Disposition.self if c.id == character_id else Disposition.ally,
                )
                for c in party
            },
        )
        context = await build_standin_context(session, character=character, game_state=state)
        timeline = await scoped_timeline_text(
            session, game_session=game_session, character=character
        )
        control_seq = control.seq
        await session.commit()  # Do not hold a DB transaction across a model request.
        await realtime.hub.broadcast(game_session.id, {**status, "thinking": True})
        decision = await asyncio.wait_for(
            asyncio.to_thread(
                decide_action,
                client,
                context,
                timeline_text=timeline,
                model=os.environ.get("STANDIN_MODEL", DEFAULT_MODEL),
            ),
            timeout=25,
        )
        await session.execute(
            select(GameSession.id).where(GameSession.id == game_session.id).with_for_update()
        )
        await session.refresh(game_session)
        await session.refresh(character)
        latest = await control_event(session, game_session, character_id)
        latest_seq = latest.seq if latest else None
        # A player taking back control or changing boundaries cancels this result.
        session.expire_all()
        await session.refresh(game_session)
        await session.refresh(character)
        updated_context = await build_standin_context(
            session, character=character, game_state=state
        )
        if (
            game_session.status != SessionStatus.active
            or latest is None
            or latest_seq != control_seq
            or updated_context != context
        ):
            raise HTTPException(
                409, "The session or character changed; this AI turn was discarded."
            )
        event = await repository.append_event(
            session,
            game_session=game_session,
            kind=event_kind_for(decision),
            actor_label=character.name,
            body=decision.summary,
            ai_generated=True,
            payload={
                **event_payload(decision),
                "request_id": str(body.request_id),
                "character_id": str(character_id),
            },
        )
        await session.commit()
        await realtime.hub.broadcast(game_session.id, frame(event))
        return frame(event)
    except TimeoutError as exc:
        raise HTTPException(
            504, "The stand-in took too long. You can retry or play the turn yourself."
        ) from exc
    except (anthropic.APIError, StandInError, ValueError, KeyError, TypeError) as exc:
        logger.warning("stand-in turn failed (%s)", type(exc).__name__)
        raise HTTPException(502, "The stand-in could not complete its turn. Please retry.") from exc
    finally:
        _busy.discard(game_session.id)
        await realtime.hub.broadcast(game_session.id, {**status, "thinking": False})
