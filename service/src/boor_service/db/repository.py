"""Core persistence operations that enforce campaign/invite invariants (DATA-01).

These wrap the multi-step flows where an invariant must hold (create a campaign
*and* its owner's DM membership atomically; accept an invite only if it's still
valid). Invalid state raises ``ValueError`` — matching the rules engine's style,
and per project convention we surface the real error rather than swallowing it.

Callers own the transaction: these functions ``flush`` but do not ``commit``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.db.models import (
    Campaign,
    Invite,
    InviteStatus,
    Membership,
    MembershipRole,
    User,
)

logger = logging.getLogger(__name__)


async def create_campaign_with_owner(
    session: AsyncSession, *, name: str, owner: User
) -> Campaign:
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


async def accept_invite(
    session: AsyncSession, *, token: str, user: User
) -> Membership:
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

    membership = Membership(
        campaign_id=invite.campaign_id, user_id=user.id, role=invite.role
    )
    session.add(membership)
    invite.status = InviteStatus.accepted
    invite.accepted_by_id = user.id
    invite.accepted_at = datetime.now(UTC)
    await session.flush()
    logger.info("user %s accepted invite %s", user.id, invite.id)
    return membership
