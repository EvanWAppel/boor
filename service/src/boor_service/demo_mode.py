"""Demo-request detection for the public, sign-in-free demo (PLAT-DEMO-01).

The browser calls this service directly from the web app's page, so the service
never sees the demo web hostname as its own ``Host``. It sees it as the request's
``Origin``, which browsers send on every cross-origin fetch and every WebSocket
handshake. A request whose ``Origin`` is a demo origin is a *demo request* for its
whole lifetime, including background tasks it schedules.

Demo mode can only lower privilege: a demo request reads and writes the separate
demo schema (:mod:`boor_service.db.demo`), authenticates only synthetic guests, and
never calls a paid API. So a spoofed ``Origin`` reaches the sandbox and nothing more.

``BOOR_DEMO=1`` is the local switch: every request is a demo request. Off by default.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import HTTPException, status
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

#: The public demo's web origin; override (comma-separated) with ``DEMO_ORIGINS``.
DEFAULT_DEMO_ORIGINS = ("https://boor-demo.evanappel.me",)
NOT_IN_DEMO = "Not available in the demo. Sign in on the main site to do this."

_active: ContextVar[bool] = ContextVar("boor_demo_request", default=False)


def forced() -> bool:
    """The local switch: ``BOOR_DEMO=1`` makes every request a demo request."""
    return os.environ.get("BOOR_DEMO") == "1"


def demo_origins() -> tuple[str, ...]:
    configured = os.environ.get("DEMO_ORIGINS")
    if configured is None:
        return DEFAULT_DEMO_ORIGINS
    return tuple(o.strip() for o in configured.split(",") if o.strip())


def is_demo_origin(origin: str | None) -> bool:
    return forced() or (origin is not None and origin in demo_origins())


def active() -> bool:
    """Whether the current request is a demo request (False outside any request)."""
    return _active.get()


@contextmanager
def activated() -> Iterator[None]:
    """Run a block as a demo request (the middleware's seam; also used by tests)."""
    token = _active.set(True)
    try:
        yield
    finally:
        _active.reset(token)


class DemoOriginMiddleware:
    """Mark HTTP and WebSocket requests from a demo origin as demo requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        origin = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"origin"), None)
        if not is_demo_origin(origin):
            await self.app(scope, receive, send)
            return
        with activated():
            await self.app(scope, receive, send)


async def not_in_demo() -> None:
    """Route dependency: refuse actions that would reach outside a guest's sandbox."""
    if active():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=NOT_IN_DEMO)
