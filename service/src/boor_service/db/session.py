"""Async engine + session factory for the running service (DATA-01).

Reads ``DATABASE_URL`` from the environment (Railway provides it). We normalize
the scheme to the asyncpg driver and drop libpq-only query params (e.g.
``sslmode``) that asyncpg does not accept, raising loudly if the URL is missing —
per project convention we do not hide configuration errors.

Tests do **not** use this module; they build their own engine against an ephemeral
testcontainers Postgres (see ``tests/conftest.py``).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from functools import lru_cache
from urllib.parse import urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# libpq params that psycopg understands but asyncpg does not; stripped from the URL.
_LIBPQ_ONLY_PARAMS = frozenset({"sslmode", "channel_binding"})


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"
    query_pairs = [
        (k, v)
        for k, v in _parse_query(parts.query)
        if k not in _LIBPQ_ONLY_PARAMS
    ]
    return urlunsplit(parts._replace(scheme=scheme, query=urlencode(query_pairs)))


def _parse_query(query: str) -> list[tuple[str, str]]:
    if not query:
        return []
    return [
        (k, v)
        for pair in query.split("&")
        for k, _, v in [pair.partition("=")]
    ]


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Process-wide async engine, built from ``DATABASE_URL``."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set; cannot connect to Postgres")
    return create_async_engine(_normalize_url(url), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker:
    """Process-wide async session factory."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped session dependency: commit on success, roll back on error.

    A FastAPI-shaped async generator (no framework import needed). Repository
    functions only ``flush``; this owns the transaction boundary so a handler's
    writes land exactly when the request succeeds.
    """
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
