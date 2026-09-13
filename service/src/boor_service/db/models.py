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
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from boor_service.ai.actions import ActionType
from boor_service.ai.guardrails import RedLine, RedLineKind
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


class SessionStatus(enum.StrEnum):
    """Lifecycle of a single play session."""

    scheduled = "scheduled"
    active = "active"
    ended = "ended"


class RiskTolerance(enum.StrEnum):
    """How much danger a stand-in should court on the player's behalf (DATA-04)."""

    cautious = "cautious"
    balanced = "balanced"
    bold = "bold"
    reckless = "reckless"


class EventKind(enum.StrEnum):
    """Kind of entry in a session's unified timeline (DATA-03).

    The 'story log' is the narrative subset (see :data:`STORY_KINDS`); the rest
    are mechanical/structured entries.
    """

    roll = "roll"
    action = "action"
    move = "move"
    turn = "turn"
    narration = "narration"
    in_character = "in_character"
    out_of_character = "out_of_character"
    system = "system"


class EventAudience(enum.StrEnum):
    """Who may know a session event (DATA-07 / build-primer §4.2).

    * ``table`` — everyone at the table (the default; public play).
    * ``characters`` — only the characters listed in ``visible_to``.
    * ``dm`` — the human DM only; stand-ins never see these.
    """

    table = "table"
    characters = "characters"
    dm = "dm"


#: Event kinds that make up the readable story log (narrative prose).
STORY_KINDS = frozenset({EventKind.narration, EventKind.in_character})


# Shared Enum type objects — reused across columns so the PG type is created once.
_ROLE_ENUM = Enum(MembershipRole, name="membership_role")
_INVITE_STATUS_ENUM = Enum(InviteStatus, name="invite_status")
_SESSION_STATUS_ENUM = Enum(SessionStatus, name="session_status")
_EVENT_KIND_ENUM = Enum(EventKind, name="event_kind")
_EVENT_AUDIENCE_ENUM = Enum(EventAudience, name="event_audience")
_RISK_TOLERANCE_ENUM = Enum(RiskTolerance, name="risk_tolerance")
# Reuses the same RedLineKind the pure checker evaluates, so persisted red lines
# round-trip straight back into boor_service.ai.guardrails.check_action.
_RED_LINE_KIND_ENUM = Enum(RedLineKind, name="red_line_kind")

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
    sessions: Mapped[list[GameSession]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    characters: Mapped[list[Character]] = relationship(
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
    status: Mapped[InviteStatus] = mapped_column(_INVITE_STATUS_ENUM, default=InviteStatus.pending)
    invited_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    accepted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    campaign: Mapped[Campaign] = relationship(back_populates="invites")


class GameSession(UUIDPrimaryKey, Timestamped, Base):
    """A single play session of a campaign (DATA-03).

    Named ``GameSession`` to avoid confusion with a SQLAlchemy DB session.
    """

    __tablename__ = "game_sessions"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(200), default=None)
    status: Mapped[SessionStatus] = mapped_column(
        _SESSION_STATUS_ENUM, default=SessionStatus.scheduled
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    campaign: Mapped[Campaign] = relationship(back_populates="sessions")
    events: Mapped[list[SessionEvent]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionEvent.seq",
    )


class SessionEvent(UUIDPrimaryKey, Timestamped, Base):
    """One entry in a session's unified, ordered timeline (DATA-03).

    ``seq`` is a per-session monotonic ordinal; the unique constraint guards
    against gaps/collisions if two writes race. ``payload`` holds structured data
    (dice result, coords, ...), ``body`` holds prose (narration, chat).
    ``ai_generated`` marks stand-in / AI-DM actions for attribution (AI-08).
    ``audience`` + ``visible_to`` are the per-character knowledge scope
    (DATA-07): a stand-in reasons only over events its character knows.
    """

    __tablename__ = "session_events"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_session_event_seq"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[EventKind] = mapped_column(_EVENT_KIND_ENUM)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True
    )
    actor_label: Mapped[str | None] = mapped_column(String(120), default=None)
    body: Mapped[str | None] = mapped_column(String, default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    audience: Mapped[EventAudience] = mapped_column(
        _EVENT_AUDIENCE_ENUM, default=EventAudience.table
    )
    visible_to: Mapped[list[str]] = mapped_column(JSONB, default=list)

    session: Mapped[GameSession] = relationship(back_populates="events")
    actor: Mapped[User | None] = relationship()


class Character(UUIDPrimaryKey, Timestamped, Base):
    """A player character in a campaign (DATA-02 persistence).

    Stores the durable *inputs* of a 5e sheet — name, level, and the
    ability/proficiency data needed to reconstruct the in-memory
    :class:`boor_service.character.Character` domain model; derived stats (AC,
    initiative, ...) are recomputed, never persisted. ``sheet`` is a JSONB blob so
    the rich, still-evolving domain model stays reworkable without a migration per
    field (mirrors how :attr:`SessionEvent.payload` is stored). ``player_id`` is
    the member who controls this character — nullable for NPCs or not-yet-claimed
    pregens (``SET NULL`` so deleting a user doesn't delete their party).
    """

    __tablename__ = "characters"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    level: Mapped[int] = mapped_column(Integer, default=1)
    sheet: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    campaign: Mapped[Campaign] = relationship(back_populates="characters")
    player: Mapped[User | None] = relationship()
    profile: Mapped[PersonalityProfile | None] = relationship(
        back_populates="character", cascade="all, delete-orphan", uselist=False
    )
    red_lines: Mapped[list[CharacterRedLine]] = relationship(
        back_populates="character",
        cascade="all, delete-orphan",
        order_by="CharacterRedLine.position",
    )


class PersonalityProfile(UUIDPrimaryKey, Timestamped, Base):
    """A character's stand-in persona and standing instructions (DATA-04).

    Exactly one per character (unique ``character_id``). ``persona`` is the
    voice/personality prose the stand-in speaks in; ``standing_instructions`` is
    the player's free-text guidance ("play cautious, protect Pip");
    ``risk_tolerance`` tunes how much danger the stand-in courts; ``traits`` holds
    the structured questionnaire capture (goals, quirks, relationships, voice
    notes — AI-01). These feed :class:`~boor_service.ai.standin.StandInContext`.
    """

    __tablename__ = "personality_profiles"

    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), unique=True, index=True
    )
    persona: Mapped[str] = mapped_column(String, default="")
    standing_instructions: Mapped[str] = mapped_column(String, default="")
    risk_tolerance: Mapped[RiskTolerance] = mapped_column(
        _RISK_TOLERANCE_ENUM, default=RiskTolerance.balanced
    )
    traits: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    character: Mapped[Character] = relationship(back_populates="profile")


class CharacterRedLine(UUIDPrimaryKey, Timestamped, Base):
    """A persisted standing red line for a character's stand-in (DATA-04 / AI-02).

    The DB row for a :class:`boor_service.ai.guardrails.RedLine`: ``kind`` reuses
    the same ``RedLineKind`` enum the pure checker evaluates, and ``entity_ids`` /
    ``action_types`` persist that kind's parameters as JSON lists. ``position``
    preserves evaluation order — ``check_action`` is order-sensitive (first
    violation wins), so ordering must survive a round-trip. :meth:`as_red_line`
    rebuilds the frozen domain object the checker consumes.
    """

    __tablename__ = "character_red_lines"

    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[RedLineKind] = mapped_column(_RED_LINE_KIND_ENUM)
    entity_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    action_types: Mapped[list[str]] = mapped_column(JSONB, default=list)
    note: Mapped[str] = mapped_column(String, default="")

    character: Mapped[Character] = relationship(back_populates="red_lines")

    def as_red_line(self) -> RedLine:
        """Rebuild the frozen domain red line that ``check_action`` evaluates."""
        return RedLine(
            kind=self.kind,
            entity_ids=frozenset(self.entity_ids),
            action_types=frozenset(ActionType(a) for a in self.action_types),
            note=self.note,
        )
