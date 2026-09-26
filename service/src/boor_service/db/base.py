"""Declarative base and shared column mixins (DATA-01).

Every table gets a UUID primary key and a timezone-aware ``created_at``. Keeping
these in mixins is the DRY convention the rest of the schema builds on.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all boor ORM models."""


class UUIDPrimaryKey:
    """Mixin: a client-generatable UUID primary key.

    Generated Python-side (``uuid4``) so an object has its id before flush,
    which keeps repository code that wires up relationships straightforward.
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class Timestamped:
    """Mixin: a server-set ``created_at`` timestamp (UTC, tz-aware)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
