"""X-02: one structured usage record per model call (model, tokens, latency).

Every model call path (stand-in, adjudicator, recap) wraps its ``create`` call in
:func:`track_usage`. On exit — success or exception — exactly one INFO line is
logged on ``boor_service.ai.usage`` with ``key=value`` fields, and the same data
rides on the log record as ``record.model_usage`` (a :class:`ModelUsage`) for
structured handlers and tests. Only counts and identifiers are logged: never
prompt text, persona, timeline or player input.

Per-session totals are not persisted: ``GameSession`` has no column for them and
adding one needs a migration, which is out of scope for this slice. Aggregate the
log lines instead.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

CallKind = Literal["standin", "adjudicator", "recap"]


@dataclass(frozen=True)
class ModelUsage:
    call: str
    #: The model that answered (a server-side fallback may differ from the request);
    #: the requested model when no response came back.
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    #: ``ok`` when the API returned a response, ``error`` when the call raised.
    outcome: Literal["ok", "error"]


@dataclass
class _Tracker:
    response: Any = None


def _int_or_none(value: object) -> int | None:
    return value if type(value) is int else None


@contextmanager
def track_usage(call: CallKind, model: str) -> Iterator[_Tracker]:
    """Time a model call and log its usage. Set ``tracker.response`` inside the block."""
    tracker = _Tracker()
    start = time.perf_counter()
    try:
        yield tracker
    finally:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        response = tracker.response
        usage = getattr(response, "usage", None)
        record = ModelUsage(
            call=call,
            model=str(getattr(response, "model", None) or model),
            input_tokens=_int_or_none(getattr(usage, "input_tokens", None)),
            output_tokens=_int_or_none(getattr(usage, "output_tokens", None)),
            latency_ms=latency_ms,
            outcome="ok" if response is not None else "error",
        )
        logger.info(
            "model usage call=%s model=%s input_tokens=%s output_tokens=%s "
            "latency_ms=%s outcome=%s",
            *asdict(record).values(),
            extra={"model_usage": record},
        )
