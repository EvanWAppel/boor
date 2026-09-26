"""Tests for the core schema and its invariants (DATA-01).

Runs against an ephemeral testcontainers Postgres (see ``conftest.py``) so we
exercise real constraints, enums, and cascades — not a SQLite approximation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.db.models import (
    Campaign,
    Invite,
    InviteStatus,
    Membership,
    MembershipRole,
    User,
)
from boor_service.db.repository import (
    accept_invite,
    create_campaign_with_owner,
    invite_player,
)

UserFactory = Callable[..., Awaitable[User]]


async def test_user_persists_with_uuid_and_timestamp(
    make_user: UserFactory,
) -> None:
    user = await make_user(email="dm@example.com")
    assert user.id is not None
    assert user.created_at is not None
    assert user.email == "dm@example.com"


async def test_duplicate_clerk_id_rejected(
    session: AsyncSession, make_user: UserFactory
) -> None:
    await make_user(clerk_user_id="clerk_dup", email="a@example.com")
    session.add(User(clerk_user_id="clerk_dup", email="b@example.com"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_duplicate_email_rejected(
    session: AsyncSession, make_user: UserFactory
) -> None:
    await make_user(email="dup@example.com", clerk_user_id="clerk_x")
    session.add(User(clerk_user_id="clerk_y", email="dup@example.com"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_campaign_gives_owner_a_dm_membership(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="The Ninth Toll", owner=owner)

    memberships = (
        await session.execute(
            select(Membership).where(Membership.campaign_id == campaign.id)
        )
    ).scalars().all()
    assert len(memberships) == 1
    assert memberships[0].user_id == owner.id
    assert memberships[0].role is MembershipRole.dm


async def test_membership_unique_per_campaign_and_user(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Twice", owner=owner)
    session.add(
        Membership(campaign_id=campaign.id, user_id=owner.id, role=MembershipRole.player)
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_invite_gets_unique_token_and_pending_status(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Party", owner=owner)

    first = await invite_player(
        session, campaign=campaign, email="p1@example.com", invited_by=owner
    )
    second = await invite_player(
        session, campaign=campaign, email="p2@example.com", invited_by=owner
    )
    assert first.token and second.token
    assert first.token != second.token
    assert first.status is InviteStatus.pending
    assert first.role is MembershipRole.player


async def test_accept_invite_creates_membership_and_marks_accepted(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    player = await make_user()
    campaign = await create_campaign_with_owner(session, name="Join Me", owner=owner)
    invite = await invite_player(
        session, campaign=campaign, email="p@example.com", invited_by=owner
    )

    membership = await accept_invite(session, token=invite.token, user=player)

    assert membership.campaign_id == campaign.id
    assert membership.user_id == player.id
    assert membership.role is MembershipRole.player
    assert invite.status is InviteStatus.accepted
    assert invite.accepted_by_id == player.id
    assert invite.accepted_at is not None


async def test_accept_unknown_token_raises(
    session: AsyncSession, make_user: UserFactory
) -> None:
    player = await make_user()
    with pytest.raises(ValueError, match="not found"):
        await accept_invite(session, token="nope", user=player)


async def test_accept_already_accepted_invite_raises(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    player = await make_user()
    other = await make_user()
    campaign = await create_campaign_with_owner(session, name="Once", owner=owner)
    invite = await invite_player(
        session, campaign=campaign, email="p@example.com", invited_by=owner
    )
    await accept_invite(session, token=invite.token, user=player)

    with pytest.raises(ValueError, match="not pending"):
        await accept_invite(session, token=invite.token, user=other)


async def test_accept_expired_invite_raises_and_marks_expired(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    player = await make_user()
    campaign = await create_campaign_with_owner(session, name="Too Late", owner=owner)
    invite = await invite_player(
        session,
        campaign=campaign,
        email="p@example.com",
        invited_by=owner,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    with pytest.raises(ValueError, match="expired"):
        await accept_invite(session, token=invite.token, user=player)
    assert invite.status is InviteStatus.expired


async def test_accept_when_already_member_raises(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Owner Joins", owner=owner)
    invite = await invite_player(
        session, campaign=campaign, email=owner.email, invited_by=owner
    )
    # owner already has a DM membership from campaign creation
    with pytest.raises(ValueError, match="already a member"):
        await accept_invite(session, token=invite.token, user=owner)


async def test_deleting_campaign_cascades_to_memberships_and_invites(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Doomed", owner=owner)
    await invite_player(
        session, campaign=campaign, email="p@example.com", invited_by=owner
    )

    obj = await session.get(Campaign, campaign.id)
    assert obj is not None
    await session.delete(obj)
    await session.flush()

    remaining_members = (
        await session.execute(select(Membership).where(Membership.campaign_id == campaign.id))
    ).scalars().all()
    remaining_invites = (
        await session.execute(select(Invite).where(Invite.campaign_id == campaign.id))
    ).scalars().all()
    assert remaining_members == []
    assert remaining_invites == []
