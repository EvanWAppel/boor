"""Core persistence operations that enforce campaign/invite invariants (DATA-01).

These wrap the multi-step flows where an invariant must hold (create a campaign
*and* its owner's DM membership atomically; accept an invite only if it's still
valid). Invalid state raises ``ValueError`` — matching the rules engine's style,
and per project convention we surface the real error rather than swallowing it.

Callers own the transaction: these functions ``flush`` but do not ``commit``.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from boor_service.ai.guardrails import RedLine
from boor_service.db.models import (
    STORY_KINDS,
    Campaign,
    Character,
    CharacterRedLine,
    EventAudience,
    EventKind,
    GameSession,
    Invite,
    InviteStatus,
    Membership,
    MembershipRole,
    PersonalityProfile,
    RiskTolerance,
    SessionEvent,
    SessionStatus,
    User,
)
from boor_service.knowledge import is_visible, normalize_visibility

logger = logging.getLogger(__name__)


async def sync_user(
    session: AsyncSession,
    *,
    clerk_user_id: str,
    email: str | None = None,
    display_name: str | None = None,
) -> User:
    """Get-or-create the local mirror of a Clerk identity (auth is Clerk, D-03).

    Called on every authenticated request: the first time we see a ``clerk_user_id``
    we create the row (an ``email`` is required — configure Clerk's JWT template to
    expose it); afterwards we keep the mirror fresh if the email/name changed.
    """
    user = (
        await session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    ).scalar_one_or_none()

    if user is None:
        if not email:
            raise ValueError(
                "cannot mirror a new user without an email "
                "(configure the Clerk JWT template to include 'email')"
            )
        user = User(clerk_user_id=clerk_user_id, email=email, display_name=display_name)
        session.add(user)
        await session.flush()
        logger.info("mirrored new user %s from Clerk", clerk_user_id)
        return user

    if email and user.email != email:
        user.email = email
    if display_name and user.display_name != display_name:
        user.display_name = display_name
    await session.flush()
    return user


async def campaigns_for_user(session: AsyncSession, *, user_id: uuid.UUID) -> list[Membership]:
    """The caller's memberships, campaign eagerly loaded — one per campaign joined."""
    result = await session.execute(
        select(Membership)
        .where(Membership.user_id == user_id)
        .options(selectinload(Membership.campaign))
        .order_by(Membership.created_at)
    )
    return list(result.scalars().all())


async def get_character(session: AsyncSession, *, character_id: uuid.UUID) -> Character | None:
    """Load a character by id, or ``None`` if it doesn't exist."""
    return await session.get(Character, character_id)


async def characters_in_campaign(
    session: AsyncSession, *, campaign_id: uuid.UUID
) -> list[Character]:
    """Every character in a campaign, in creation order."""
    result = await session.execute(
        select(Character).where(Character.campaign_id == campaign_id).order_by(Character.created_at)
    )
    return list(result.scalars().all())


async def campaign_members(session: AsyncSession, *, campaign_id: uuid.UUID) -> list[Membership]:
    """A campaign's memberships with their users eagerly loaded, in join order."""
    result = await session.execute(
        select(Membership)
        .where(Membership.campaign_id == campaign_id)
        .options(selectinload(Membership.user))
        .order_by(Membership.created_at)
    )
    return list(result.scalars().all())


async def create_campaign_with_owner(session: AsyncSession, *, name: str, owner: User) -> Campaign:
    """Create a campaign and its owner's DM membership together."""
    campaign = Campaign(name=name, owner_id=owner.id)
    # Append via the relationship: the UUID pk is generated at flush time, so
    # letting the ORM wire up campaign_id avoids a null FK on the membership.
    campaign.memberships.append(Membership(user_id=owner.id, role=MembershipRole.dm))
    session.add(campaign)
    await session.flush()
    logger.info("created campaign %s owned by user %s", campaign.id, owner.id)
    return campaign


async def invite_player(
    session: AsyncSession,
    *,
    campaign: Campaign,
    email: str,
    invited_by: User,
    role: MembershipRole = MembershipRole.player,
    expires_at: datetime | None = None,
) -> Invite:
    """Create a pending invite for ``email`` to join ``campaign``."""
    invite = Invite(
        campaign_id=campaign.id,
        email=email,
        invited_by_id=invited_by.id,
        role=role,
        expires_at=expires_at,
    )
    session.add(invite)
    await session.flush()
    logger.info("invited %s to campaign %s (invite %s)", email, campaign.id, invite.id)
    return invite


async def accept_invite(session: AsyncSession, *, token: str, user: User) -> Membership:
    """Redeem an invite ``token`` for ``user``, creating their membership.

    Raises ``ValueError`` if the token is unknown, the invite is not pending, it
    has expired, or the user already belongs to the campaign.
    """
    invite = (
        await session.execute(select(Invite).where(Invite.token == token))
    ).scalar_one_or_none()
    if invite is None:
        raise ValueError("invite token not found")
    if invite.status is not InviteStatus.pending:
        raise ValueError(f"invite is {invite.status.value}, not pending")
    if invite.expires_at is not None and invite.expires_at < datetime.now(UTC):
        invite.status = InviteStatus.expired
        await session.flush()
        raise ValueError("invite has expired")

    already_member = (
        await session.execute(
            select(Membership).where(
                Membership.campaign_id == invite.campaign_id,
                Membership.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if already_member is not None:
        raise ValueError("user is already a member of this campaign")

    membership = Membership(campaign_id=invite.campaign_id, user_id=user.id, role=invite.role)
    session.add(membership)
    invite.status = InviteStatus.accepted
    invite.accepted_by_id = user.id
    invite.accepted_at = datetime.now(UTC)
    await session.flush()
    logger.info("user %s accepted invite %s", user.id, invite.id)
    return membership


async def create_character(
    session: AsyncSession,
    *,
    campaign: Campaign,
    name: str,
    level: int = 1,
    sheet: dict[str, Any] | None = None,
    player: User | None = None,
) -> Character:
    """Create a character in ``campaign``, optionally controlled by ``player``."""
    character = Character(
        campaign_id=campaign.id,
        name=name,
        level=level,
        sheet=sheet if sheet is not None else {},
        player_id=player.id if player is not None else None,
    )
    session.add(character)
    await session.flush()
    logger.info("created character %s (%s) in campaign %s", character.id, name, campaign.id)
    return character


async def set_personality_profile(
    session: AsyncSession,
    *,
    character: Character,
    persona: str = "",
    standing_instructions: str = "",
    risk_tolerance: RiskTolerance = RiskTolerance.balanced,
    traits: dict[str, Any] | None = None,
) -> PersonalityProfile:
    """Create or update a character's single personality profile (upsert, DATA-04)."""
    profile = (
        await session.execute(
            select(PersonalityProfile).where(PersonalityProfile.character_id == character.id)
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = PersonalityProfile(character_id=character.id)
        session.add(profile)
    profile.persona = persona
    profile.standing_instructions = standing_instructions
    profile.risk_tolerance = risk_tolerance
    profile.traits = traits if traits is not None else {}
    await session.flush()
    logger.info("set personality profile for character %s", character.id)
    return profile


async def personality_profile_for(
    session: AsyncSession, *, character: Character
) -> PersonalityProfile | None:
    """A character's personality profile, or ``None`` if none has been set yet."""
    return (
        await session.execute(
            select(PersonalityProfile).where(PersonalityProfile.character_id == character.id)
        )
    ).scalar_one_or_none()


async def add_red_line(
    session: AsyncSession, *, character: Character, red_line: RedLine
) -> CharacterRedLine:
    """Append a standing red line to a character, preserving evaluation order.

    ``position`` is ``max(position) + 1`` (starting at 0) so the order red lines
    were added is the order ``check_action`` evaluates them — first violation wins.
    """
    next_position = (
        await session.execute(
            select(func.coalesce(func.max(CharacterRedLine.position), -1)).where(
                CharacterRedLine.character_id == character.id
            )
        )
    ).scalar_one() + 1
    row = CharacterRedLine(
        character_id=character.id,
        position=next_position,
        kind=red_line.kind,
        entity_ids=sorted(red_line.entity_ids),
        action_types=sorted(action_type.value for action_type in red_line.action_types),
        note=red_line.note,
    )
    session.add(row)
    await session.flush()
    logger.info("added red line %s to character %s", red_line.kind.value, character.id)
    return row


async def red_lines_for(session: AsyncSession, *, character: Character) -> tuple[RedLine, ...]:
    """A character's standing red lines as domain objects, in evaluation order.

    The tuple is ready to hand straight to ``check_action`` /
    :class:`~boor_service.ai.standin.StandInContext`.
    """
    rows = (
        (
            await session.execute(
                select(CharacterRedLine)
                .where(CharacterRedLine.character_id == character.id)
                .order_by(CharacterRedLine.position)
            )
        )
        .scalars()
        .all()
    )
    return tuple(row.as_red_line() for row in rows)


async def create_session(
    session: AsyncSession,
    *,
    campaign: Campaign,
    title: str | None = None,
    status: SessionStatus = SessionStatus.scheduled,
) -> GameSession:
    """Create a play session for ``campaign``.

    A session created directly as ``active`` gets its ``started_at`` stamped.
    """
    game_session = GameSession(campaign_id=campaign.id, title=title, status=status)
    if status is SessionStatus.active:
        game_session.started_at = datetime.now(UTC)
    session.add(game_session)
    await session.flush()
    logger.info("created session %s for campaign %s", game_session.id, campaign.id)
    return game_session


async def append_event(
    session: AsyncSession,
    *,
    game_session: GameSession,
    kind: EventKind,
    actor: User | None = None,
    actor_label: str | None = None,
    body: str | None = None,
    payload: dict[str, Any] | None = None,
    ai_generated: bool = False,
    audience: EventAudience | str = EventAudience.table,
    visible_to: Sequence[uuid.UUID | str] | None = None,
) -> SessionEvent:
    """Append an entry to a session's timeline, assigning the next ``seq``.

    ``seq`` is ``max(seq) + 1`` for the session (starting at 1). Lock the parent
    session until commit so simultaneous speakers cannot claim the same seq.
    ``audience`` / ``visible_to`` are the DATA-07 knowledge scope; default is
    public to the table so existing chat/dice callers stay unchanged.
    """
    parsed_audience, parsed_visible_to = normalize_visibility(audience, visible_to)
    await session.execute(
        select(GameSession.id).where(GameSession.id == game_session.id).with_for_update()
    )
    next_seq = (
        await session.execute(
            select(func.coalesce(func.max(SessionEvent.seq), 0)).where(
                SessionEvent.session_id == game_session.id
            )
        )
    ).scalar_one() + 1
    event = SessionEvent(
        session_id=game_session.id,
        seq=next_seq,
        kind=kind,
        actor_user_id=actor.id if actor is not None else None,
        actor_label=actor_label,
        body=body,
        payload=payload if payload is not None else {},
        ai_generated=ai_generated,
        audience=parsed_audience,
        visible_to=parsed_visible_to,
    )
    session.add(event)
    await session.flush()
    return event


async def end_session(session: AsyncSession, *, game_session: GameSession) -> GameSession:
    """Mark a session ended and stamp ``ended_at``."""
    game_session.status = SessionStatus.ended
    game_session.ended_at = datetime.now(UTC)
    await session.flush()
    logger.info("ended session %s", game_session.id)
    return game_session


async def story_log(session: AsyncSession, *, game_session: GameSession) -> list[SessionEvent]:
    """The narrative subset of a session's timeline, in order (the 'story log')."""
    result = await session.execute(
        select(SessionEvent)
        .where(
            SessionEvent.session_id == game_session.id,
            SessionEvent.kind.in_(STORY_KINDS),
        )
        .order_by(SessionEvent.seq)
    )
    return list(result.scalars().all())


async def sessions_for_campaign(
    session: AsyncSession, *, campaign_id: uuid.UUID
) -> list[GameSession]:
    """Every play session of a campaign, newest first (for the session picker)."""
    result = await session.execute(
        select(GameSession)
        .where(GameSession.campaign_id == campaign_id)
        .order_by(GameSession.created_at.desc())
    )
    return list(result.scalars().all())


async def session_timeline(
    session: AsyncSession, *, game_session: GameSession
) -> list[SessionEvent]:
    """The full ordered timeline of a session — every kind, for room replay.

    Unlike :func:`story_log` (the narrative subset), this is the complete record
    a joining client replays to catch up: chat, dice rolls, turns, and system
    events, in ``seq`` order. This is the *unscoped* record — the DM's view.
    Stand-ins and players must use :func:`timeline_for_character` /
    :func:`timeline_for_viewer` so they cannot see what they shouldn't.
    """
    result = await session.execute(
        select(SessionEvent)
        .where(SessionEvent.session_id == game_session.id)
        .order_by(SessionEvent.seq)
    )
    return list(result.scalars().all())


async def timeline_for_character(
    session: AsyncSession, *, game_session: GameSession, character: Character
) -> list[SessionEvent]:
    """Events this character knows — the stand-in's only legal view of the record.

    Filters the session timeline through :func:`boor_service.knowledge.is_visible`
    with ``is_dm=False``. A secret the rogue took in a private channel will not
    appear here for the paladin, even though it is in the campaign record.
    """
    events = await session_timeline(session, game_session=game_session)
    character_id = str(character.id)
    return [
        event
        for event in events
        if is_visible(event.audience, event.visible_to, character_ids=(character_id,), is_dm=False)
    ]


async def timeline_for_viewer(
    session: AsyncSession, *, game_session: GameSession, viewer: User
) -> list[SessionEvent]:
    """Events a human at the table may see: DM sees all, a player sees table + theirs.

    Used by ``GET /sessions/{id}/log`` so a late-joining player cannot replay a
    whisper they weren't in. The DM is omniscient as a viewer (not as a stand-in).
    """
    membership = (
        await session.execute(
            select(Membership).where(
                Membership.campaign_id == game_session.campaign_id,
                Membership.user_id == viewer.id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        return []
    if membership.role is MembershipRole.dm:
        return await session_timeline(session, game_session=game_session)

    characters = await characters_in_campaign(session, campaign_id=game_session.campaign_id)
    character_ids = tuple(str(c.id) for c in characters if c.player_id == viewer.id)
    events = await session_timeline(session, game_session=game_session)
    return [
        event
        for event in events
        if is_visible(event.audience, event.visible_to, character_ids=character_ids, is_dm=False)
    ]


def render_timeline(events: Sequence[SessionEvent]) -> str:
    """Prompt-ready rendering of an already-scoped timeline.

    Callers must pass a *scoped* list (from :func:`timeline_for_character`); this
    function does not re-filter. An empty timeline is an explicit "nothing yet"
    so the stand-in isn't staring at a blank user message.
    """
    if not events:
        return "(nothing has happened yet this session)"
    lines: list[str] = []
    for event in events:
        who = event.actor_label or "the table"
        marker = "[AI] " if event.ai_generated else ""
        body = event.body or f"({event.kind.value})"
        lines.append(f"{event.seq}. {marker}{who}: {body}")
    return "\n".join(lines)


async def reveal_event_to(
    session: AsyncSession, *, event: SessionEvent, character: Character
) -> SessionEvent:
    """Grant a character knowledge of an event (a secret becomes known).

    A ``table`` event is already public — no-op. A ``dm`` note becomes a
    ``characters`` whisper to this character. A ``characters`` event adds the
    character to ``visible_to`` if they weren't already on it.
    """
    character_id = str(character.id)
    if event.audience is EventAudience.table:
        return event
    if event.audience is EventAudience.dm:
        event.audience = EventAudience.characters
        event.visible_to = [character_id]
    elif character_id not in event.visible_to:
        event.visible_to = [*event.visible_to, character_id]
    await session.flush()
    return event
