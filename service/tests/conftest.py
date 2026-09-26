"""Shared pytest fixtures for the boor service test suite.

Per project conventions we DRY test setup via fixtures here.
"""

from __future__ import annotations

import itertools
import random
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator

import httpx
import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from boor_service.api import app
from boor_service.auth.clerk import ClerkVerifier
from boor_service.auth.dependencies import get_verifier
from boor_service.db.base import Base
from boor_service.db.models import User
from boor_service.db.session import get_session

#: Issuer the test Clerk verifier trusts (see the auth fixtures below).
CLERK_ISSUER_TEST = "https://clerk.example.test"


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


# --- Clerk auth fixtures (local keypair; no network / real Clerk) -----------


@pytest.fixture(scope="session")
def clerk_keypair() -> tuple[str, str]:
    """A (private_pem, public_pem) RSA pair, generated once for the test session."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


@pytest.fixture
def clerk_verifier(clerk_keypair: tuple[str, str]) -> ClerkVerifier:
    """A verifier that trusts the test keypair's public key (injected resolver)."""
    _, public_pem = clerk_keypair
    return ClerkVerifier(
        issuer=CLERK_ISSUER_TEST,
        signing_key_resolver=lambda _token: public_pem,
        audience=None,
    )


@pytest.fixture
def mint_token(clerk_keypair: tuple[str, str]) -> Callable[..., str]:
    """Factory minting Clerk-shaped RS256 JWTs signed by the test keypair."""
    private_pem, _ = clerk_keypair

    def _mint(
        *,
        sub: str | None = "clerk_user_1",
        email: str | None = "user@example.com",
        name: str | None = "User",
        iss: str = CLERK_ISSUER_TEST,
        exp_delta: int = 3600,
        private_pem_override: str | None = None,
        omit: tuple[str, ...] = (),
    ) -> str:
        now = int(time.time())
        claims: dict[str, object] = {"iat": now, "exp": now + exp_delta, "iss": iss}
        if sub is not None:
            claims["sub"] = sub
        if email is not None:
            claims["email"] = email
        if name is not None:
            claims["name"] = name
        for key in omit:
            claims.pop(key, None)
        return jwt.encode(
            claims, private_pem_override or private_pem, algorithm="RS256", headers={"kid": "test"}
        )

    return _mint


@pytest_asyncio.fixture
async def session_log_seeder(
    session: AsyncSession,
) -> Callable[..., Awaitable[None]]:
    """Append a couple of timeline events to a session, as the realtime handler would.

    Shares the test's single session (the same one ``auth_client`` reads through),
    so seeded events are visible to a subsequent ``GET /sessions/{id}/log``.
    """
    from boor_service.db.models import EventKind, GameSession
    from boor_service.db.repository import append_event

    async def _seed(session_id: str) -> None:
        game_session = await session.get(GameSession, uuid.UUID(session_id))
        assert game_session is not None
        await append_event(
            session,
            game_session=game_session,
            kind=EventKind.narration,
            body="The door creaks open.",
        )
        await append_event(
            session,
            game_session=game_session,
            kind=EventKind.roll,
            body="Perception",
            payload={"total": 12},
        )
        await session.commit()

    return _seed


@pytest_asyncio.fixture
async def auth_client(
    session: AsyncSession, clerk_verifier: ClerkVerifier
) -> AsyncIterator[httpx.AsyncClient]:
    """An httpx client bound to the app, with DB + verifier overridden for tests.

    ``get_session`` yields the test's single session (so writes persist across
    requests within a test), and ``get_verifier`` returns the local-keypair
    verifier. Pair with :func:`mint_token` to authenticate requests.
    """

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_verifier] = lambda: clerk_verifier
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
