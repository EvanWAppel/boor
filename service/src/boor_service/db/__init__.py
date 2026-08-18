"""Persistence layer for the boor service (DATA-01).

Locked architecture (see ``boor/DECISIONS.md``): the Python service **owns all
data** (BFF) — it is the only thing that touches Postgres — and runs on Railway
alongside a co-located Railway Postgres. SQLAlchemy 2.0 (async, asyncpg) + Alembic.
"""

from __future__ import annotations

from boor_service.db.base import Base
from boor_service.db.models import (
    STORY_KINDS,
    Campaign,
    Character,
    CharacterRedLine,
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
from boor_service.db.session import get_engine, get_sessionmaker

__all__ = [
    "STORY_KINDS",
    "Base",
    "Campaign",
    "Character",
    "CharacterRedLine",
    "EventKind",
    "GameSession",
    "Invite",
    "InviteStatus",
    "Membership",
    "MembershipRole",
    "PersonalityProfile",
    "RiskTolerance",
    "SessionEvent",
    "SessionStatus",
    "User",
    "get_engine",
    "get_sessionmaker",
]
