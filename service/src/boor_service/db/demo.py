"""The demo database: guest sandboxes in their own schema (PLAT-DEMO-01).

Demo requests (see :mod:`boor_service.demo_mode`) get sessions from here, never
from the real engine. The demo engine connects with ``search_path`` set to
:data:`SCHEMA` *only*, so an unqualified table name can't resolve to a real table.
It uses ``DEMO_DATABASE_URL`` when set, else the same server as ``DATABASE_URL``.

The schema is disposable: built from the ORM metadata (not migrations) the first
time a demo request arrives in this process, then dropped and rebuilt every
``DEMO_RESET_HOURS`` (default 24). Nothing is created until someone uses the demo.

Each guest is a browser holding a random token ``demo.<32 hex>``. The first time
the service sees a token it creates that guest and seeds their own guided-play
campaign, so visitors never share a table. ``DEMO_MAX_GUESTS`` (default 500)
caps the sandboxes between resets. No real emails exist here: guests are
``guest-<hex>@demo.invalid``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from functools import lru_cache

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from boor_service.auth.clerk import AuthError
from boor_service.db.base import Base
from boor_service.db.models import RiskTolerance, SessionStatus, User
from boor_service.db.repository import (
    create_campaign_with_owner,
    create_character,
    create_session,
    set_personality_profile,
)
from boor_service.db.seed import thora_sheet
from boor_service.db.session import _normalize_url

logger = logging.getLogger(__name__)

SCHEMA = "boor_demo"
GUEST_PREFIX = "demo_guest_"
_TOKEN = re.compile(r"demo\.([0-9a-f]{32})")


class DemoFull(Exception):
    """The guest cap is reached until the next reset."""


def _reset_seconds() -> float:
    return float(os.environ.get("DEMO_RESET_HOURS", "24")) * 3600


def _max_guests() -> int:
    return int(os.environ.get("DEMO_MAX_GUESTS", "500"))


@lru_cache(maxsize=1)
def engine() -> AsyncEngine:
    url = os.environ.get("DEMO_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DEMO_DATABASE_URL or DATABASE_URL must be set to serve the demo")
    # A small, bounded pool: demo traffic can never take the shared server's
    # connections from the real host. Past the bound, demo requests wait, then fail.
    return create_async_engine(
        _normalize_url(url),
        pool_size=3,
        max_overflow=2,
        pool_timeout=5,
        connect_args={"server_settings": {"search_path": SCHEMA}},
    )


@lru_cache(maxsize=1)
def sessionmaker() -> async_sessionmaker:
    return async_sessionmaker(engine(), expire_on_commit=False)


class _State:
    built_at: float | None = None
    lock: asyncio.Lock | None = None


_state = _State()


def forget() -> None:
    """Drop cached engine and build state (tests; the next demo request rebuilds)."""
    engine.cache_clear()
    sessionmaker.cache_clear()
    _state.built_at = None
    _state.lock = None


async def dispose() -> None:
    if engine.cache_info().currsize:
        await engine().dispose()
    forget()


async def reset() -> None:
    """Drop the demo schema and rebuild it empty."""
    async with engine().begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        # Isolation rests on search_path; refuse to build anything if it isn't ours alone
        # (e.g. a pooler that drops startup parameters).
        schemas = (await conn.execute(text("SELECT current_schemas(false)"))).scalar()
        if schemas != [SCHEMA]:
            raise RuntimeError(f"demo engine search_path is {schemas}, expected [{SCHEMA!r}]")
        await conn.run_sync(Base.metadata.create_all)
    _state.built_at = time.monotonic()
    logger.info("demo schema %s reset", SCHEMA)


async def ensure_ready() -> None:
    """Build the schema on first use, and rebuild it once it is older than the period."""
    built = _state.built_at
    if built is not None and time.monotonic() - built < _reset_seconds():
        return
    if _state.lock is None:
        _state.lock = asyncio.Lock()
    async with _state.lock:
        built = _state.built_at
        if built is None or time.monotonic() - built >= _reset_seconds():
            await reset()


def guest_id(token: str | None) -> str:
    """The guest id in a ``demo.<32 hex>`` token; :class:`AuthError` otherwise."""
    match = _TOKEN.fullmatch(token or "")
    if match is None:
        raise AuthError("demo requests need a guest token (demo.<32 hex>)")
    return match.group(1)


async def guest_user(session: AsyncSession, token: str | None) -> User:
    """The guest for ``token``, creating them and their sandbox on first sight.

    Raises :class:`AuthError` for a malformed token and :class:`DemoFull` when the
    guest cap is reached.
    """
    gid = guest_id(token)
    clerk_user_id = GUEST_PREFIX + gid
    by_id = select(User).where(User.clerk_user_id == clerk_user_id)
    if user := await session.scalar(by_id):
        return user
    # Serialize first sight of a guest, so parallel first requests seed once.
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(clerk_user_id))))
    if user := await session.scalar(by_id):
        return user
    guests = await session.scalar(
        select(func.count()).select_from(User).where(User.clerk_user_id.startswith(GUEST_PREFIX))
    )
    if (guests or 0) >= _max_guests():
        raise DemoFull("The demo is full right now. Please try again later.")
    user = User(
        clerk_user_id=clerk_user_id, email=f"guest-{gid}@demo.invalid", display_name="Guest"
    )
    session.add(user)
    await session.flush()
    await seed_sandbox(session, user)
    return user


async def seed_sandbox(session: AsyncSession, guest: User) -> None:
    """The guest's own table: they host it, own a character, and have a session open."""
    campaign = await create_campaign_with_owner(session, name="The River Road (demo)", owner=guest)
    thora = await create_character(
        session, campaign=campaign, name="Thora", level=5, sheet=thora_sheet(), player=guest
    )
    await set_personality_profile(
        session,
        character=thora,
        persona="Blunt, brave, fiercely protective of her companions.",
        standing_instructions="Protect the healer. Don't flee a winnable fight.",
        risk_tolerance=RiskTolerance.bold,
        traits={"goals": ["keep the party alive"]},
    )
    await create_session(
        session, campaign=campaign, title="Guided adventure", status=SessionStatus.active
    )
    logger.info("seeded demo sandbox campaign %s for guest %s", campaign.id, guest.id)
