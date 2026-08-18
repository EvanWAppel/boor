"""Tests for the realtime session room (VTT-01).

Exercises the WebSocket connection handler by calling it directly with a fake
socket — same in-loop, real-DB style as the auth dependency tests, so there's no
TestClient event-loop juggling. Covers the auth handshake (token + membership),
presence broadcast, chat relay + timeline persistence, and multi-socket fan-out.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.auth.clerk import ClerkVerifier
from boor_service.db.models import SessionEvent, User
from boor_service.db.repository import (
    create_campaign_with_owner,
    create_session,
    sync_user,
)
from boor_service.realtime import (
    WS_FORBIDDEN,
    WS_NOT_FOUND,
    WS_UNAUTHORIZED,
    Presence,
    SessionHub,
    handle_connection,
)

TokenFactory = Callable[..., str]


class FakeWebSocket:
    """A scripted stand-in for Starlette's WebSocket (see ``realtime.WebSocketLike``)."""

    def __init__(self, *, token: str | None, incoming: list[Any] | None = None) -> None:
        self.query_params: dict[str, str] = {"token": token} if token is not None else {}
        self._incoming = iter(incoming or [])
        self.sent: list[Any] = []
        self.accepted = False
        self.close_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def receive_json(self) -> Any:
        from fastapi import WebSocketDisconnect

        try:
            return next(self._incoming)
        except StopIteration:
            raise WebSocketDisconnect(code=1000) from None

    async def send_json(self, data: Any) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.close_code = code


async def _member_session(
    session: AsyncSession, *, clerk_id: str, email: str, name: str = "Player"
) -> tuple[User, uuid.UUID]:
    """A user who owns a campaign with one game session; returns (user, session_id)."""
    user = await sync_user(session, clerk_user_id=clerk_id, email=email, display_name=name)
    campaign = await create_campaign_with_owner(session, name="Table", owner=user)
    game_session = await create_session(session, campaign=campaign)
    return user, game_session.id


# --- auth handshake --------------------------------------------------------


async def test_missing_token_closes_unauthorized(
    session: AsyncSession, clerk_verifier: ClerkVerifier
) -> None:
    ws = FakeWebSocket(token=None)
    await handle_connection(ws, uuid.uuid4(), session, clerk_verifier, SessionHub())
    assert ws.close_code == WS_UNAUTHORIZED


async def test_invalid_token_closes_unauthorized(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    ws = FakeWebSocket(token=mint_token(exp_delta=-3600))  # expired
    await handle_connection(ws, uuid.uuid4(), session, clerk_verifier, SessionHub())
    assert ws.close_code == WS_UNAUTHORIZED


async def test_unknown_session_closes_not_found(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    token = mint_token(sub="clerk_a", email="a@example.com")
    ws = FakeWebSocket(token=token)
    await handle_connection(ws, uuid.uuid4(), session, clerk_verifier, SessionHub())
    assert ws.close_code == WS_NOT_FOUND


async def test_non_member_closes_forbidden(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    _owner, session_id = await _member_session(
        session, clerk_id="clerk_owner", email="owner@example.com"
    )
    # a different, un-joined user tries to connect
    ws = FakeWebSocket(token=mint_token(sub="clerk_outsider", email="out@example.com"))
    await handle_connection(ws, session_id, session, clerk_verifier, SessionHub())
    assert ws.close_code == WS_FORBIDDEN


# --- presence + chat -------------------------------------------------------


async def test_member_joins_and_chat_persists_to_timeline(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    user, session_id = await _member_session(
        session, clerk_id="clerk_p", email="p@example.com", name="Pip"
    )
    token = mint_token(sub="clerk_p", email="p@example.com", name="Pip")
    ws = FakeWebSocket(token=token, incoming=[{"type": "chat", "body": "Well met."}])

    await handle_connection(ws, session_id, session, clerk_verifier, SessionHub())

    assert ws.accepted and ws.close_code is None
    # a presence 'join' then the echoed chat (self leave isn't sent to a removed socket)
    kinds = [m.get("type") for m in ws.sent]
    assert kinds == ["presence", "chat"]
    assert ws.sent[0]["event"] == "join"
    assert ws.sent[1]["body"] == "Well met."

    # the chat landed on the session timeline (DATA-03)
    events = (
        await session.execute(
            select(SessionEvent).where(SessionEvent.session_id == session_id)
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].body == "Well met."
    assert events[0].actor_user_id == user.id
    assert events[0].ai_generated is False


async def test_broadcast_reaches_other_sockets_including_leave(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    _user, session_id = await _member_session(
        session, clerk_id="clerk_h", email="h@example.com", name="Host"
    )
    room = SessionHub()
    # a second member already connected in the same room (pre-registered)
    observer = FakeWebSocket(token=None)
    room.join(session_id, observer, Presence(user_id=str(uuid.uuid4()), display_name="Observer"))

    token = mint_token(sub="clerk_h", email="h@example.com", name="Host")
    joiner = FakeWebSocket(token=token, incoming=[{"type": "chat", "body": "hi"}])
    await handle_connection(joiner, session_id, session, clerk_verifier, room)

    # observer sees the joiner's join, chat, and leave
    events = [(m.get("type"), m.get("event")) for m in observer.sent]
    assert ("presence", "join") in events
    assert ("chat", None) in events
    assert ("presence", "leave") in events
    # room is empty of the joiner afterward; observer remains
    assert joiner not in [s for s in room._rooms.get(session_id, {})]


# --- hub unit behavior -----------------------------------------------------


async def test_hub_roster_and_broadcast_exclude() -> None:
    hub = SessionHub()
    sid = uuid.uuid4()
    a = FakeWebSocket(token=None)
    b = FakeWebSocket(token=None)
    hub.join(sid, a, Presence(user_id="a", display_name="A"))
    hub.join(sid, b, Presence(user_id="b", display_name="B"))

    assert {p.user_id for p in hub.roster(sid)} == {"a", "b"}

    await hub.broadcast(sid, {"type": "ping"}, exclude=a)
    assert a.sent == []
    assert b.sent == [{"type": "ping"}]

    hub.leave(sid, a)
    hub.leave(sid, b)
    assert hub.roster(sid) == []
