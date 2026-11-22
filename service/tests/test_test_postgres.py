"""The throwaway test Postgres skips durability so the suite stays fast on slow disks.

The fleet box (satellite) runs tests on a 5400rpm HDD, where every per-test
``drop_all``/``create_all`` paid for fsyncs: 13.5 min there vs 2.5 min in CI,
against the fleet daemon's 20-min test timeout. See DECISIONS.md (fleet join).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.parametrize("setting", ["fsync", "synchronous_commit", "full_page_writes"])
async def test_test_postgres_skips_durability(session: AsyncSession, setting: str) -> None:
    assert (await session.execute(text(f"SHOW {setting}"))).scalar_one() == "off"
