"""Optional LangSmith tracing for eval runs.

Off by default. Set ``BOOR_LANGSMITH=1`` *and* install ``langsmith`` to trace the
suite in LangSmith; otherwise this is a no-op. Kept behind a soft import so the
project takes no hard dependency on LangSmith.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Iterator

logger = logging.getLogger(__name__)


def tracing_enabled() -> bool:
    return bool(os.getenv("BOOR_LANGSMITH"))


@contextlib.contextmanager
def traced_run(name: str) -> Iterator[None]:
    """Wrap a run in a LangSmith trace when enabled; a no-op otherwise."""
    if not tracing_enabled():
        yield
        return
    try:
        from langsmith import trace  # type: ignore
    except ImportError:
        logger.warning("BOOR_LANGSMITH is set but langsmith is not installed; skipping tracing")
        yield
        return
    with trace(name=name, run_type="chain"):
        yield
