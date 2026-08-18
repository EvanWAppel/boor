"""FastAPI auth dependencies: token -> user, and per-campaign role gating (AUTH-03).

Composable dependencies the routes declare:

* :func:`get_current_user` — verify the ``Bearer`` token and return the local
  :class:`~boor_service.db.models.User` (mirrored on first login).
* :func:`current_membership` — the caller's membership in the ``campaign_id`` from
  the path, or 403 if they don't belong to that campaign.
* :func:`require_dm` — narrows the above to the campaign's DM.

Verification failures are 401; authorization failures are 403 — each carries the
real reason, per project convention. The verifier and DB session are injected, so
tests can call these functions directly with a local-keypair verifier and an
ephemeral session.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.requests import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.auth.clerk import AuthError, ClerkVerifier, verifier_from_env
from boor_service.db import repository
from boor_service.db.models import Character, Membership, MembershipRole, User
from boor_service.db.session import get_session

logger = logging.getLogger(__name__)


def get_verifier() -> ClerkVerifier:
    """The process-wide Clerk verifier (dependency seam; overridable in tests)."""
    return verifier_from_env()


#: Injection aliases (FastAPI's Annotated style; keeps `Depends` out of defaults).
SessionDep = Annotated[AsyncSession, Depends(get_session)]
VerifierDep = Annotated[ClerkVerifier, Depends(get_verifier)]


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or malformed Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_current_user(
    request: Request,
    session: SessionDep,
    verifier: VerifierDep,
) -> User:
    """Verify the request's Clerk token and return the mirrored local user."""
    token = _bearer_token(request)
    try:
        identity = verifier.verify(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    try:
        return await repository.sync_user(
            session,
            clerk_user_id=identity.clerk_user_id,
            email=identity.email,
            display_name=identity.display_name,
        )
    except ValueError as exc:
        # e.g. the token carried no email claim, so we can't create the mirror.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc


CurrentUser = Annotated[User, Depends(get_current_user)]


async def _load_membership(
    session: AsyncSession, *, campaign_id: uuid.UUID, user_id: uuid.UUID
) -> Membership | None:
    return (
        await session.execute(
            select(Membership).where(
                Membership.campaign_id == campaign_id,
                Membership.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def current_membership(
    campaign_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
) -> Membership:
    """The caller's membership in ``campaign_id``, or 403 if they aren't a member."""
    membership = await _load_membership(session, campaign_id=campaign_id, user_id=user.id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not a member of this campaign",
        )
    return membership


CurrentMembership = Annotated[Membership, Depends(current_membership)]


async def require_dm(membership: CurrentMembership) -> Membership:
    """Narrow :func:`current_membership` to the campaign's DM (else 403)."""
    if membership.role is not MembershipRole.dm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this action requires the campaign DM role",
        )
    return membership


RequireDM = Annotated[Membership, Depends(require_dm)]


async def _character_in_reach(
    session: AsyncSession, *, character_id: uuid.UUID, user: User
) -> tuple[Character, Membership]:
    """Load a character and the caller's membership in its campaign.

    404 if the character is gone; 403 if the caller isn't in its campaign.
    """
    character = await repository.get_character(session, character_id=character_id)
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="character not found"
        )
    membership = await _load_membership(
        session, campaign_id=character.campaign_id, user_id=user.id
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not a member of this character's campaign",
        )
    return character, membership


async def character_for_member(
    character_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Character:
    """A character any member of its campaign may read."""
    character, _membership = await _character_in_reach(
        session, character_id=character_id, user=user
    )
    return character


async def character_for_editor(
    character_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Character:
    """A character the caller may edit — its own player, or the campaign DM."""
    character, membership = await _character_in_reach(
        session, character_id=character_id, user=user
    )
    if character.player_id != user.id and membership.role is not MembershipRole.dm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only the character's player or the campaign DM may edit it",
        )
    return character


CharacterForMember = Annotated[Character, Depends(character_for_member)]
CharacterForEditor = Annotated[Character, Depends(character_for_editor)]
