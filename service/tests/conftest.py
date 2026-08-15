"""Shared pytest fixtures for the boor service test suite.

Per project conventions we DRY test setup via fixtures here.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from boor_service.api import app
from boor_service.db.base import Base
from boor_service.db.models import User


@pytest.fixture
def rng() -> random.Random:
    """A seeded RNG so dice tests are deterministic and repeatable."""
    return random.Random(1234)


@pytest.fixture
def client() -> TestClient:
    """HTTP client bound to the FastAPI app for endpoint tests."""
    return TestClient(app)


@pytest.fixture(scope="session")
def _postgres_container() -> Iterator[PostgresContainer]:
    """One ephemeral Postgres for the whole test session (testcontainers)."""
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg


@pytest_asyncio.fixture
async def session(_postgres_container: PostgresContainer) -> AsyncIterator[AsyncSession]:
    """A fresh async session against a freshly-created schema for each test.

    A per-test engine with ``NullPool`` sidesteps asyncpg's loop-bound pooling,
    and drop+create gives each test an isolated, empty database.
    """
    engine = create_async_engine(
        _postgres_container.get_connection_url(), poolclass=NullPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as db_session:
            yield db_session
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def make_user(
    session: AsyncSession,
) -> Callable[..., Awaitable[User]]:
    """Factory for persisted ``User`` rows with unique clerk id/email defaults."""
    counter = itertools.count(1)

    async def _make(**overrides: object) -> User:
        n = next(counter)
        user = User(
            clerk_user_id=overrides.get("clerk_user_id", f"clerk_{n}"),
            email=overrides.get("email", f"user{n}@example.com"),
            display_name=overrides.get("display_name"),
        )
        session.add(user)
        await session.flush()
        return user

    return _make
