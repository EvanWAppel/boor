"""Core schema: users, campaigns, memberships, invites (DATA-01).

Users are a local mirror of Clerk identities (auth is Clerk — see D-03): each row
is keyed by ``clerk_user_id`` and created on first login. A campaign has one owner
(its DM) plus per-campaign memberships (DM vs player, AUTH-03) and invite links
(AUTH-02).

Enums are declared once and shared across columns so the Postgres ``CREATE TYPE``
happens exactly once.
"""

from __future__ import annotations

import enum
import secrets
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from boor_service.db.base import Base, Timestamped, UUIDPrimaryKey


class MembershipRole(enum.StrEnum):
    """A member's role within a single campaign."""

    dm = "dm"
    player = "player"


class InviteStatus(enum.StrEnum):
    """Lifecycle of a campaign invite."""

    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"
    expired = "expired"


# Shared Enum type objects — reused across columns so the PG type is created once.
_ROLE_ENUM = Enum(MembershipRole, name="membership_role")
_INVITE_STATUS_ENUM = Enum(InviteStatus, name="invite_status")

_TOKEN_BYTES = 32


def new_invite_token() -> str:
    """A URL-safe, unguessable token for an invite link."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


class User(UUIDPrimaryKey, Timestamped, Base):
    """A person, mirrored from Clerk on first login."""

    __tablename__ = "users"

    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)


class Campaign(UUIDPrimaryKey, Timestamped, Base):
    """A game/table, owned by the DM who created it."""

    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    owner: Mapped[User] = relationship()
    memberships: Mapped[list[Membership]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    invites: Mapped[list[Invite]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class Membership(UUIDPrimaryKey, Timestamped, Base):
    """A user's role in a campaign. One membership per (campaign, user)."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("campaign_id", "user_id", name="uq_membership_campaign_user"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MembershipRole] = mapped_column(_ROLE_ENUM)

    campaign: Mapped[Campaign] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship()


class Invite(UUIDPrimaryKey, Timestamped, Base):
    """An invitation to join a campaign, redeemable by link token (AUTH-02)."""

    __tablename__ = "invites"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, default=new_invite_token
    )
    role: Mapped[MembershipRole] = mapped_column(_ROLE_ENUM, default=MembershipRole.player)
    status: Mapped[InviteStatus] = mapped_column(
        _INVITE_STATUS_ENUM, default=InviteStatus.pending
    )
    invited_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    accepted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    campaign: Mapped[Campaign] = relationship(back_populates="invites")
