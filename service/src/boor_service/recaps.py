"""AI-09: character recaps — written at session end, read in-app before the next one.

Decided by Evan 2026-10-10: when the DM ends a session, every character the AI
stand-in played (at least one stand-in turn) gets a recap in their own voice,
written in a background task (:func:`generate`). It is private to the character's
player and the DM until the player shares it with the table; the player marks it
read and may flag lines as out of character (kept for AI-10), but the text is never
rewritten. A failed write is kept as ``failed`` with its reason, and the DM can
retry. Email delivery is deferred (BLOCKED.md).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

import anthropic
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from boor_service.ai.adjudicator import SupportsBetaMessages
from boor_service.ai.recap import DEFAULT_MODEL, RecapContext, Written, write_recap
from boor_service.auth.dependencies import CurrentMembership, CurrentUser, SessionDep
from boor_service.db import repository
from boor_service.db.models import (
    Character,
    CharacterRecap,
    GameSession,
    Membership,
    MembershipRole,
    PersonalityProfile,
    RecapFlag,
    RecapStatus,
    SessionEvent,
)
from boor_service.db.session import get_sessionmaker

router = APIRouter()
logger = logging.getLogger(__name__)

AI_OFF = "AI recaps are not enabled on this table."
#: A pending recap older than this is presumed lost (restart, crash) and retryable.
STALE_PENDING = timedelta(minutes=5)
#: Bound on "not my character" flags per recap.
MAX_FLAGS = 20


def get_client() -> SupportsBetaMessages | None:
    """The model client, or ``None`` when stand-ins (and so recaps) are not enabled."""
    if os.environ.get("ENABLE_STANDINS") != "1" or not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return cast(SupportsBetaMessages, anthropic.Anthropic(timeout=60, max_retries=0))


async def write(client: SupportsBetaMessages, ctx: RecapContext) -> Written:
    model = os.environ.get("RECAP_MODEL", DEFAULT_MODEL)
    return await asyncio.wait_for(
        asyncio.to_thread(write_recap, client, ctx, model=model), timeout=90
    )


# --- Creation and writing -----------------------------------------------------


async def create_pending(db: AsyncSession, game_session: GameSession) -> list[uuid.UUID]:
    """Add a pending recap for each character the stand-in took a turn for.

    Idempotent per (session, character). Returns the ids of recaps created now.
    """
    played = await db.scalars(
        select(SessionEvent.payload["character_id"].astext)
        .where(
            SessionEvent.session_id == game_session.id,
            SessionEvent.ai_generated.is_(True),
            SessionEvent.payload.has_key("character_id"),
        )
        .distinct()
    )
    existing = set(
        await db.scalars(
            select(CharacterRecap.character_id).where(CharacterRecap.session_id == game_session.id)
        )
    )
    created: list[uuid.UUID] = []
    for raw in played:
        character_id = uuid.UUID(raw)
        if character_id in existing or await db.get(Character, character_id) is None:
            continue
        # Explicit id: the column default only applies at flush, and we return it now.
        recap = CharacterRecap(
            id=uuid.uuid4(), session_id=game_session.id, character_id=character_id
        )
        db.add(recap)
        created.append(recap.id)
    await db.flush()
    if created:
        logger.info("session %s: %d recap(s) to write", game_session.id, len(created))
    return created


async def build_context(db: AsyncSession, recap: CharacterRecap) -> RecapContext:
    """Everything the writer may see: the character's scoped view only (DATA-07)."""
    game = await db.get(GameSession, recap.session_id)
    character = await db.get(Character, recap.character_id)
    if game is None or character is None:
        raise LookupError(f"recap {recap.id} lost its session or character")
    profile = await db.scalar(
        select(PersonalityProfile).where(PersonalityProfile.character_id == character.id)
    )
    events = await repository.timeline_for_character(db, game_session=game, character=character)
    own = [
        e.body or ""
        for e in events
        if e.ai_generated and e.payload.get("character_id") == str(character.id)
    ]
    return RecapContext(
        character_name=character.name,
        persona=profile.persona if profile else "",
        standing_instructions=profile.standing_instructions if profile else "",
        session_title=game.title or "Untitled session",
        timeline=repository.render_timeline(events),
        own_actions=own,
    )


async def generate(sessions: async_sessionmaker, recap_id: uuid.UUID) -> None:
    """Background task: write one recap and store the result (ready or failed).

    The outermost frame of a background task, so every failure is logged with its
    traceback and recorded on the recap (the DM sees it and can retry) rather than
    lost; a recap is never left silently pending by an error here.
    """
    written: Written | None = None
    error = ""
    client = None
    try:
        client = get_client()
        async with sessions() as db:
            recap = await db.get(CharacterRecap, recap_id)
            if recap is None:
                logger.warning("recap %s vanished before it was written", recap_id)
                return
            ctx = await build_context(db, recap)
        if client is None:
            error = AI_OFF
        else:
            written = await write(client, ctx)
    except Exception as exc:
        logger.exception("writing recap %s failed", recap_id)
        error = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()
    status = RecapStatus.ready if written is not None else RecapStatus.failed
    values: dict[str, object] = (
        {"status": status, "body": written.text, "error": "", "model": written.model}
        if written is not None
        else {"status": status, "error": error}
    )
    # Only a still-pending recap is written: a finished recap is never rewritten, and
    # a late or duplicate writer (e.g. after a retry of a stale one) changes nothing.
    # If this write itself fails, the recap stays pending and becomes retryable once
    # it is older than STALE_PENDING.
    async with sessions() as db:
        result = await db.execute(
            update(CharacterRecap)
            .where(CharacterRecap.id == recap_id, CharacterRecap.status == RecapStatus.pending)
            .values(**values)
            .returning(CharacterRecap.id)
        )
        await db.commit()
    if result.first() is None:
        logger.info("recap %s was already settled; this result is discarded", recap_id)
    else:
        logger.info("recap %s is %s", recap_id, status.value)


# --- HTTP ---------------------------------------------------------------------


class FlagIn(BaseModel):
    quote: str = Field(max_length=1000)
    note: str = Field(default="", max_length=1000)


class FlagOut(BaseModel):
    quote: str
    note: str
    created_at: datetime


class RecapOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    session_title: str
    character_id: uuid.UUID
    character_name: str
    status: RecapStatus
    body: str
    #: Only shown to the DM, who can retry a failed recap.
    error: str
    shared: bool
    #: The character's player has read it (only meaningful when ``mine``).
    read: bool
    mine: bool
    #: "Not my character" flags: visible to the player and the DM only.
    flags: list[FlagOut]
    created_at: datetime


def _out(
    recap: CharacterRecap, game: GameSession, character: Character, membership: Membership
) -> RecapOut:
    mine = character.player_id == membership.user_id
    is_dm = membership.role is MembershipRole.dm
    return RecapOut(
        id=recap.id,
        session_id=game.id,
        session_title=game.title or "Untitled session",
        character_id=character.id,
        character_name=character.name,
        status=recap.status,
        body=recap.body if recap.status is RecapStatus.ready else "",
        error=recap.error if is_dm else "",
        shared=recap.shared_at is not None,
        read=recap.read_at is not None,
        mine=mine,
        flags=[FlagOut(quote=f.quote, note=f.note, created_at=f.created_at) for f in recap.flags]
        if mine or is_dm
        else [],
        created_at=recap.created_at,
    )


@router.get("/campaigns/{campaign_id}/recaps", response_model=list[RecapOut])
async def list_recaps(
    campaign_id: uuid.UUID, membership: CurrentMembership, db: SessionDep
) -> list[RecapOut]:
    """Recaps this member may read: all (DM), their own characters', and shared ones."""
    rows = (
        await db.execute(
            select(CharacterRecap, GameSession, Character)
            .join(GameSession, GameSession.id == CharacterRecap.session_id)
            .join(Character, Character.id == CharacterRecap.character_id)
            .where(GameSession.campaign_id == campaign_id)
            .options(selectinload(CharacterRecap.flags))
            .order_by(CharacterRecap.created_at.desc())
        )
    ).all()
    is_dm = membership.role is MembershipRole.dm
    return [
        _out(recap, game, character, membership)
        for recap, game, character in rows
        if is_dm or character.player_id == membership.user_id or recap.shared_at is not None
    ]


async def _recap_in_reach(
    db: AsyncSession, recap_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[CharacterRecap, GameSession, Character, Membership]:
    recap = await db.scalar(
        select(CharacterRecap)
        .where(CharacterRecap.id == recap_id)
        .options(selectinload(CharacterRecap.flags))
    )
    if recap is None:
        raise HTTPException(404, "recap not found")
    game = await db.get(GameSession, recap.session_id)
    character = await db.get(Character, recap.character_id)
    membership = (
        await db.scalar(
            select(Membership).where(
                Membership.campaign_id == game.campaign_id, Membership.user_id == user_id
            )
        )
        if game
        else None
    )
    if game is None or character is None or membership is None:
        raise HTTPException(403, "not a member of this recap's campaign")
    can_see = (
        membership.role is MembershipRole.dm
        or character.player_id == user_id
        or recap.shared_at is not None
    )
    if not can_see:
        raise HTTPException(403, "this recap is private to its player")
    return recap, game, character, membership


async def _own_recap(
    db: AsyncSession, recap_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[CharacterRecap, GameSession, Character, Membership]:
    """The caller's own, finished recap (player-only actions)."""
    found = await _recap_in_reach(db, recap_id, user_id)
    if found[2].player_id != user_id:
        raise HTTPException(403, "only this character's player can do that")
    if found[0].status is not RecapStatus.ready:
        raise HTTPException(409, "this recap isn't finished yet")
    return found


@router.post("/recaps/{recap_id}/read", response_model=RecapOut)
async def mark_read(recap_id: uuid.UUID, user: CurrentUser, db: SessionDep) -> RecapOut:
    recap, game, character, membership = await _own_recap(db, recap_id, user.id)
    recap.read_at = recap.read_at or datetime.now(UTC)
    await db.commit()
    return _out(recap, game, character, membership)


@router.post("/recaps/{recap_id}/share", response_model=RecapOut)
async def share(recap_id: uuid.UUID, user: CurrentUser, db: SessionDep) -> RecapOut:
    """Share with the whole table (player only). Logged; there is no un-share yet."""
    recap, game, character, membership = await _own_recap(db, recap_id, user.id)
    if recap.shared_at is None:
        recap.shared_at = datetime.now(UTC)
        logger.info("recap %s shared with the table by %s", recap.id, user.id)
    await db.commit()
    return _out(recap, game, character, membership)


@router.post("/recaps/{recap_id}/flags", response_model=RecapOut)
async def flag(recap_id: uuid.UUID, body: FlagIn, user: CurrentUser, db: SessionDep) -> RecapOut:
    """Flag part of the recap as out of character. The recap text is not changed."""
    recap, game, character, membership = await _own_recap(db, recap_id, user.id)
    quote = body.quote.strip()
    if not quote:
        raise HTTPException(422, "Quote the part that doesn't sound like your character.")
    if len(recap.flags) >= MAX_FLAGS:
        raise HTTPException(409, f"A recap can hold at most {MAX_FLAGS} flags.")
    recap.flags.append(RecapFlag(user_id=user.id, quote=quote, note=body.note.strip()))
    await db.commit()
    await db.refresh(recap, ["flags"])
    logger.info("recap %s flagged by %s", recap.id, user.id)
    return _out(recap, game, character, membership)


@router.post("/recaps/{recap_id}/retry", response_model=RecapOut)
async def retry(
    recap_id: uuid.UUID,
    user: CurrentUser,
    db: SessionDep,
    background: BackgroundTasks,
    sessions: Annotated[async_sessionmaker, Depends(get_sessionmaker)],
) -> RecapOut:
    """Write a failed (or stale pending) recap again (DM only).

    A finished recap is never rewritten. The claim is one conditional UPDATE, so two
    concurrent retries can't both start a write.
    """
    recap, game, character, membership = await _recap_in_reach(db, recap_id, user.id)
    if membership.role is not MembershipRole.dm:
        raise HTTPException(403, "only the DM can retry a recap")
    now = datetime.now(UTC)
    claimed = await db.execute(
        update(CharacterRecap)
        .where(
            CharacterRecap.id == recap.id,
            or_(
                CharacterRecap.status == RecapStatus.failed,
                and_(
                    CharacterRecap.status == RecapStatus.pending,
                    CharacterRecap.attempted_at < now - STALE_PENDING,
                ),
            ),
        )
        .values(status=RecapStatus.pending, error="", attempted_at=now)
        .returning(CharacterRecap.id)
    )
    if claimed.first() is None:
        raise HTTPException(409, "only a failed or stuck recap can be retried")
    await db.commit()
    # Reload explicitly (incl. flags) so _out never triggers a lazy load.
    await db.refresh(recap, ["status", "error", "attempted_at", "flags"])
    logger.info("recap %s retry by %s", recap.id, user.id)
    background.add_task(generate, sessions, recap.id)
    return _out(recap, game, character, membership)
