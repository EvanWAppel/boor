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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.auth.clerk import AuthError, ClerkVerifier
from boor_service.db import repository
from boor_service.db.models import (
    EventAudience,
    EventKind,
    GameSession,
    MembershipRole,
    SessionEvent,
    SessionStatus,
    User,
)
from boor_service.knowledge import normalize_visibility, presence_may_receive

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
    """Who a connected socket belongs to, for the room roster.

    ``role`` and ``character_ids`` are the DATA-07 fan-out keys: a private
    event is delivered only to the DM and to sockets whose characters are in
    the event's ``visible_to`` set. Defaults keep existing tests/callers
    (table-public frames) working without filling them in.
    """

    user_id: str
    display_name: str | None
    role: MembershipRole = MembershipRole.player
    character_ids: tuple[str, ...] = ()
    #: The name of the speaker's own character, used to label their in-character
    #: lines (their real ``display_name`` still labels out-of-character asides and
    #: rolls). ``None`` when they have no character yet (e.g. a DM), so we fall
    #: back to the real name.
    character_name: str | None = None


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
        people = self._rooms.get(session_id, {}).values()
        return list({person.user_id: person for person in people}.values())

    async def broadcast(
        self,
        session_id: uuid.UUID,
        message: dict[str, Any],
        *,
        exclude: WebSocketLike | None = None,
        include: WebSocketLike | None = None,
        audience: EventAudience = EventAudience.table,
        visible_to: list[str] | None = None,
    ) -> None:
        """Send ``message`` to sockets in the room that may know it.

        ``audience`` / ``visible_to`` are the DATA-07 filter (default ``table``
        = everyone, matching pre-scoping behavior). ``include`` always receives
        the frame so a speaker hears their own whisper even if their character
        isn't in ``visible_to``. A socket that errors on send is dropped from
        the room rather than aborting the whole broadcast — one dead connection
        must not silence the table.
        """
        room = self._rooms.get(session_id, {})
        allowed = list(visible_to or [])
        for socket, presence in list(room.items()):
            if socket is exclude:
                continue
            if socket is not include and not presence_may_receive(
                audience,
                allowed,
                role=presence.role,
                character_ids=presence.character_ids,
            ):
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
    membership = next((m for m in members if m.user_id == user.id), None)
    if membership is None:
        await socket.close(code=WS_FORBIDDEN)
        return None

    characters = await repository.characters_in_campaign(db, campaign_id=game_session.campaign_id)
    own_characters = [c for c in characters if c.player_id == user.id]
    presence = Presence(
        user_id=str(user.id),
        display_name=user.display_name,
        role=membership.role,
        character_ids=tuple(str(c.id) for c in own_characters),
        # A player speaks in character as their (first) character in the campaign.
        character_name=own_characters[0].name if own_characters else None,
    )
    return user, game_session, presence


# Frame types that append to the durable session timeline (DATA-03), mapped to
# their EventKind. Everything else is a pure ephemeral relay (typing, cursor,
# other non-durable UI hints). Keeping these durable is what lets a
# late joiner replay the table via GET /sessions/{id}/log and see real history.
_PERSISTED_KINDS: dict[str, EventKind] = {
    "chat": EventKind.in_character,
    "ooc": EventKind.out_of_character,
    "roll": EventKind.roll,
}


async def _handle_message(
    message: Any,
    *,
    session_id: uuid.UUID,
    user: User,
    game_session: GameSession,
    presence: Presence,
    socket: WebSocketLike,
    db: AsyncSession,
    room: SessionHub,
) -> None:
    """Relay one client message to the room; persist chat/ooc/roll to the timeline."""
    if not isinstance(message, dict) or "type" not in message:
        return  # ignore malformed frames rather than dropping the connection
    frame_type = message["type"]
    if not isinstance(frame_type, str):
        return
    if frame_type == "ping":
        await socket.send_json({"type": "pong"})
        return
    if frame_type in {*_PERSISTED_KINDS, "initiative"}:
        await db.execute(
            select(GameSession.id).where(GameSession.id == session_id).with_for_update()
        )
        await db.refresh(game_session)
        if game_session.status == SessionStatus.ended:
            await db.commit()
            await socket.send_json({"type": "error", "body": "This session has ended."})
            return
    if frame_type == "initiative":
        if presence.role is not MembershipRole.dm:
            return
        order, index = message.get("order"), message.get("activeIndex", 0)
        if (
            not isinstance(order, list)
            or len(order) > 100
            or not all(isinstance(name, str) and 0 < len(name) <= 120 for name in order)
            or type(index) is not int
            or index < 0
            or (index >= len(order) if order else index != 0)
        ):
            return
        event = await repository.append_event(
            db,
            game_session=game_session,
            kind=EventKind.turn,
            actor=user,
            actor_label=presence.display_name,
            payload={"type": "initiative", "order": order, "activeIndex": index},
        )
        await db.commit()
        await room.broadcast(
            session_id,
            {
                **event.payload,
                "seq": event.seq,
                "user_id": presence.user_id,
                "display_name": presence.display_name,
            },
        )
        return
    event_kind = _PERSISTED_KINDS.get(frame_type)
    if event_kind is not None:
        body = str(message["body"]) if message.get("body") is not None else None
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else None
        try:
            audience, visible_to = normalize_visibility(
                message.get("audience"), message.get("visible_to")
            )
        except ValueError:
            logger.info("dropping a persisted frame with invalid audience")
            return
        # The speaker knows what they said: fold their characters into the set.
        if audience is EventAudience.characters:
            visible_to = sorted(set(visible_to) | set(presence.character_ids))
        # In character, the table sees the character's name; out of character (and
        # rolls) it sees the real person. Fall back to the real name when the
        # speaker has no character (e.g. a DM speaking in character).
        label = presence.display_name
        if event_kind is EventKind.in_character:
            from boor_service.guided import latest_state

            state = await latest_state(db, session_id)
            participant = state["participants"].get(str(user.id)) if state else None
            if participant:
                label = participant["name"]
            elif presence.character_name:
                label = presence.character_name
        event = await repository.append_event(
            db,
            game_session=game_session,
            kind=event_kind,
            actor=user,
            actor_label=label,
            body=body,
            payload=payload,
            audience=audience,
            visible_to=visible_to,
        )
        await db.commit()
        await room.broadcast(
            session_id,
            {
                "type": frame_type,
                "user_id": presence.user_id,
                "display_name": label,
                "body": body,
                "payload": event.payload,
                "seq": event.seq,
                "audience": event.audience.value,
                "visible_to": list(event.visible_to),
            },
            audience=event.audience,
            visible_to=list(event.visible_to),
            include=socket,
        )
    elif frame_type in {"typing", "cursor"}:
        # Only allow client-owned ephemeral frames; server events cannot be forged.
        # Pure relay for ephemeral typed frames (typing, cursor):
        # tag the sender and fan out, no persistence.
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
    await room.broadcast(session_id, _presence_message("join", presence, room.roster(session_id)))
    try:
        # Persisted initiative survives refreshes, late joins, and service restarts.
        latest = await db.scalar(
            select(SessionEvent)
            .where(
                SessionEvent.session_id == session_id,
                SessionEvent.kind == EventKind.turn,
                SessionEvent.payload["type"].astext == "initiative",
            )
            .order_by(SessionEvent.seq.desc())
            .limit(1)
        )
        if latest is not None:
            await socket.send_json({**latest.payload, "seq": latest.seq})
        await db.commit()
        await socket.send_json({"type": "ready"})
        while True:
            message = await socket.receive_json()
            await _handle_message(
                message,
                session_id=session_id,
                user=user,
                game_session=game_session,
                presence=presence,
                socket=socket,
                db=db,
                room=room,
            )
            await db.commit()
    except WebSocketDisconnect:
        pass
    finally:
        room.leave(session_id, socket)
        logger.info("user %s left session %s room", user.id, session_id)
        await room.broadcast(
            session_id, _presence_message("leave", presence, room.roster(session_id))
        )
