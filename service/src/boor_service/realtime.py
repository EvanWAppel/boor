"""Realtime transport: a shared, authenticated WebSocket room per session (VTT-01).

Decision D-01/D-03: realtime is **self-hosted WebSockets on the service**, and the
service **verifies the Clerk token on the WS handshake** just like an HTTP call —
it never trusts the client blindly. A client connects to a game session's room
with ``?token=<clerk-jwt>``; we verify it, mirror the user, confirm they're a
member of the session's campaign, then join them to the room.

The room broadcasts presence (who's here) and relays typed messages to everyone
present. ``chat`` messages are also appended to the session timeline (DATA-03), so
the shared log and the durable record stay in sync. The connection handler is
written against small protocols (:class:`WebSocketLike`) and takes an injected DB
session + verifier, so the whole flow is unit-testable with a fake socket and a
local keypair — no live socket, no network.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.auth.clerk import AuthError, ClerkVerifier
from boor_service.db import repository
from boor_service.db.models import EventKind, GameSession, User

logger = logging.getLogger(__name__)

# Application close codes (the 4000-4999 range is reserved for app use).
WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_NOT_FOUND = 4404


class WebSocketLike(Protocol):
    """The slice of Starlette's ``WebSocket`` the handler uses (fake-able in tests)."""

    @property
    def query_params(self) -> Any: ...
    async def accept(self) -> None: ...
    async def receive_json(self) -> Any: ...
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


@dataclass(frozen=True)
class Presence:
    """Who a connected socket belongs to, for the room roster."""

    user_id: str
    display_name: str | None


class SessionHub:
    """In-process registry of live sockets per game session.

    One process owns the sockets it accepted; a multi-instance deploy would put a
    broker (Redis pub/sub) behind :meth:`broadcast`. For the single Railway service
    (locked architecture) an in-process hub is the right first step.
    """

    def __init__(self) -> None:
        self._rooms: dict[uuid.UUID, dict[WebSocketLike, Presence]] = {}

    def join(self, session_id: uuid.UUID, socket: WebSocketLike, presence: Presence) -> None:
        self._rooms.setdefault(session_id, {})[socket] = presence

    def leave(self, session_id: uuid.UUID, socket: WebSocketLike) -> None:
        room = self._rooms.get(session_id)
        if room is not None:
            room.pop(socket, None)
            if not room:
                del self._rooms[session_id]

    def roster(self, session_id: uuid.UUID) -> list[Presence]:
        return list(self._rooms.get(session_id, {}).values())

    async def broadcast(
        self,
        session_id: uuid.UUID,
        message: dict[str, Any],
        *,
        exclude: WebSocketLike | None = None,
    ) -> None:
        """Send ``message`` to every socket in the room (optionally excluding one).

        A socket that errors on send is dropped from the room rather than aborting
        the whole broadcast — one dead connection must not silence the table.
        """
        room = self._rooms.get(session_id, {})
        for socket in list(room):
            if socket is exclude:
                continue
            try:
                await socket.send_json(message)
            except Exception:
                # A broken socket must not kill the fan-out; drop it and continue.
                logger.info("dropping a socket that failed to receive a broadcast")
                room.pop(socket, None)


#: Process-wide hub the FastAPI WebSocket route uses.
hub = SessionHub()


def _presence_message(event: str, presence: Presence, roster: list[Presence]) -> dict[str, Any]:
    return {
        "type": "presence",
        "event": event,
        "user_id": presence.user_id,
        "display_name": presence.display_name,
        "present": [{"user_id": p.user_id, "display_name": p.display_name} for p in roster],
    }


async def _authorize(
    socket: WebSocketLike,
    session_id: uuid.UUID,
    token: str | None,
    db: AsyncSession,
    verifier: ClerkVerifier,
) -> tuple[User, GameSession, Presence] | None:
    """Verify the token and membership; close the socket and return None on failure."""
    if not token:
        await socket.close(code=WS_UNAUTHORIZED)
        return None
    try:
        identity = verifier.verify(token)
    except AuthError:
        await socket.close(code=WS_UNAUTHORIZED)
        return None

    try:
        user = await repository.sync_user(
            db,
            clerk_user_id=identity.clerk_user_id,
            email=identity.email,
            display_name=identity.display_name,
        )
    except ValueError:
        await socket.close(code=WS_UNAUTHORIZED)
        return None

    game_session = await db.get(GameSession, session_id)
    if game_session is None:
        await socket.close(code=WS_NOT_FOUND)
        return None

    members = await repository.campaign_members(db, campaign_id=game_session.campaign_id)
    if not any(m.user_id == user.id for m in members):
        await socket.close(code=WS_FORBIDDEN)
        return None

    presence = Presence(user_id=str(user.id), display_name=user.display_name)
    return user, game_session, presence


async def _handle_message(
    message: Any,
    *,
    session_id: uuid.UUID,
    user: User,
    game_session: GameSession,
    presence: Presence,
    db: AsyncSession,
    room: SessionHub,
) -> None:
    """Relay one client message to the room; persist chat to the timeline."""
    if not isinstance(message, dict) or "type" not in message:
        return  # ignore malformed frames rather than dropping the connection
    kind = message["type"]
    if kind == "chat":
        body = str(message.get("body", ""))
        event = await repository.append_event(
            db,
            game_session=game_session,
            kind=EventKind.in_character,
            actor=user,
            actor_label=presence.display_name,
            body=body,
        )
        await db.commit()
        await room.broadcast(
            session_id,
            {
                "type": "chat",
                "user_id": presence.user_id,
                "display_name": presence.display_name,
                "body": body,
                "seq": event.seq,
            },
        )
    else:
        # Pure relay for other typed frames (cursor, token move, ...): tag the
        # sender and fan out. Persistence for those kinds lands with their features.
        await room.broadcast(
            session_id,
            {**message, "user_id": presence.user_id, "display_name": presence.display_name},
        )


async def handle_connection(
    socket: WebSocketLike,
    session_id: uuid.UUID,
    db: AsyncSession,
    verifier: ClerkVerifier,
    room: SessionHub,
) -> None:
    """Accept, authenticate, and run one client's connection to a session room."""
    await socket.accept()
    token = socket.query_params.get("token")
    authorized = await _authorize(socket, session_id, token, db, verifier)
    if authorized is None:
        return
    user, game_session, presence = authorized

    room.join(session_id, socket, presence)
    logger.info("user %s joined session %s room", user.id, session_id)
    await room.broadcast(
        session_id, _presence_message("join", presence, room.roster(session_id))
    )
    try:
        while True:
            message = await socket.receive_json()
            await _handle_message(
                message,
                session_id=session_id,
                user=user,
                game_session=game_session,
                presence=presence,
                db=db,
                room=room,
            )
    except WebSocketDisconnect:
        pass
    finally:
        room.leave(session_id, socket)
        logger.info("user %s left session %s room", user.id, session_id)
        await room.broadcast(
            session_id, _presence_message("leave", presence, room.roster(session_id))
        )
