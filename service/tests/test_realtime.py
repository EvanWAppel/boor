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
from boor_service.db.models import (
    EventAudience,
    EventKind,
    MembershipRole,
    SessionEvent,
    User,
)
from boor_service.db.repository import (
    accept_invite,
    create_campaign_with_owner,
    create_character,
    create_session,
    invite_player,
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
    assert kinds == ["presence", "ready", "chat"]
    assert ws.sent[0]["event"] == "join"
    assert ws.sent[2]["body"] == "Well met."

    # the chat landed on the session timeline (DATA-03)
    events = (
        (await session.execute(select(SessionEvent).where(SessionEvent.session_id == session_id)))
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].body == "Well met."
    assert events[0].actor_user_id == user.id
    assert events[0].ai_generated is False


async def test_in_character_uses_character_name_out_of_character_uses_real_name(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    """A player's IC line is labelled with their character; OOC keeps their real name."""
    user = await sync_user(
        session, clerk_user_id="clerk_ic", email="ic@example.com", display_name="Evil Evan"
    )
    campaign = await create_campaign_with_owner(session, name="Table", owner=user)
    await create_character(session, campaign=campaign, name="Thorin", player=user)
    game_session = await create_session(session, campaign=campaign)

    token = mint_token(sub="clerk_ic", email="ic@example.com", name="Evil Evan")
    ws = FakeWebSocket(
        token=token,
        incoming=[
            {"type": "chat", "body": "For the mountain!"},
            {"type": "ooc", "body": "back in five"},
        ],
    )
    await handle_connection(ws, game_session.id, session, clerk_verifier, SessionHub())

    # The echoed frames carry the label the table renders.
    chat = next(m for m in ws.sent if m.get("type") == "chat")
    ooc = next(m for m in ws.sent if m.get("type") == "ooc")
    assert chat["display_name"] == "Thorin"
    assert ooc["display_name"] == "Evil Evan"

    # And the durable timeline stores the same labels for replay.
    result = await session.execute(
        select(SessionEvent).where(SessionEvent.session_id == game_session.id)
    )
    by_kind = {e.kind: e.actor_label for e in result.scalars().all()}
    assert by_kind[EventKind.in_character] == "Thorin"
    assert by_kind[EventKind.out_of_character] == "Evil Evan"


async def test_in_character_falls_back_to_real_name_without_a_character(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    """A speaker with no character (e.g. a DM) still gets a label: their real name."""
    _user, session_id = await _member_session(
        session, clerk_id="clerk_dm_ic", email="dm_ic@example.com", name="Dungeon Master"
    )
    token = mint_token(sub="clerk_dm_ic", email="dm_ic@example.com", name="Dungeon Master")
    ws = FakeWebSocket(token=token, incoming=[{"type": "chat", "body": "The gate creaks open."}])

    await handle_connection(ws, session_id, session, clerk_verifier, SessionHub())

    chat = next(m for m in ws.sent if m.get("type") == "chat")
    assert chat["display_name"] == "Dungeon Master"


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


async def test_roll_and_ooc_frames_persist_with_their_kinds(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    user, session_id = await _member_session(
        session, clerk_id="clerk_r", email="r@example.com", name="Roller"
    )
    token = mint_token(sub="clerk_r", email="r@example.com", name="Roller")
    ws = FakeWebSocket(
        token=token,
        incoming=[
            {
                "type": "roll",
                "body": "Athletics check",
                "payload": {"total": 17, "notation": "1d20+5"},
            },
            {"type": "ooc", "body": "brb, coffee"},
        ],
    )

    await handle_connection(ws, session_id, session, clerk_verifier, SessionHub())

    # both frames were echoed with a seq (so clients can order/dedupe)
    echoed = [m for m in ws.sent if m.get("type") in ("roll", "ooc")]
    assert [m["type"] for m in echoed] == ["roll", "ooc"]
    assert echoed[0]["payload"] == {"total": 17, "notation": "1d20+5"}
    assert echoed[0]["seq"] == 1 and echoed[1]["seq"] == 2

    # both landed on the timeline with the right EventKind, actor attributed
    events = (
        (
            await session.execute(
                select(SessionEvent)
                .where(SessionEvent.session_id == session_id)
                .order_by(SessionEvent.seq)
            )
        )
        .scalars()
        .all()
    )
    assert [e.kind for e in events] == [EventKind.roll, EventKind.out_of_character]
    assert events[0].payload == {"total": 17, "notation": "1d20+5"}
    assert events[0].actor_user_id == user.id
    assert events[1].body == "brb, coffee"


async def test_ephemeral_frames_relay_without_persisting(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    _user, session_id = await _member_session(
        session, clerk_id="clerk_e", email="e@example.com", name="Ephemeral"
    )
    room = SessionHub()
    observer = FakeWebSocket(token=None)
    room.join(session_id, observer, Presence(user_id=str(uuid.uuid4()), display_name="Obs"))

    token = mint_token(sub="clerk_e", email="e@example.com", name="Ephemeral")
    joiner = FakeWebSocket(token=token, incoming=[{"type": "typing"}])
    await handle_connection(joiner, session_id, session, clerk_verifier, room)

    # the observer received the relayed frame with sender attribution...
    relayed = [m for m in observer.sent if m.get("type") == "typing"]
    assert len(relayed) == 1
    assert relayed[0]["display_name"] == "Ephemeral"
    # ...but nothing was persisted to the timeline
    events = (
        (await session.execute(select(SessionEvent).where(SessionEvent.session_id == session_id)))
        .scalars()
        .all()
    )
    assert events == []


async def test_private_chat_reaches_only_the_dm_and_the_intended_player(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    """DATA-07: a characters-audience frame is not fanned out to the rest of the table."""
    dm = await sync_user(
        session, clerk_user_id="clerk_dm_k", email="dm_k@example.com", display_name="DM"
    )
    player = await sync_user(
        session, clerk_user_id="clerk_pl_k", email="pl_k@example.com", display_name="Pip"
    )
    other = await sync_user(
        session, clerk_user_id="clerk_ot_k", email="ot_k@example.com", display_name="Oak"
    )
    campaign = await create_campaign_with_owner(session, name="Table", owner=dm)
    for member, email in ((player, player.email), (other, other.email)):
        invite = await invite_player(session, campaign=campaign, email=email, invited_by=dm)
        await accept_invite(session, token=invite.token, user=member)
    game_session = await create_session(session, campaign=campaign)
    pip = await create_character(session, campaign=campaign, name="Pip", player=player)
    await create_character(session, campaign=campaign, name="Oak", player=other)

    room = SessionHub()
    dm_ws = FakeWebSocket(token=None)
    other_ws = FakeWebSocket(token=None)
    room.join(
        game_session.id,
        dm_ws,
        Presence(
            user_id=str(dm.id),
            display_name="DM",
            role=MembershipRole.dm,
        ),
    )
    room.join(
        game_session.id,
        other_ws,
        Presence(user_id=str(other.id), display_name="Oak"),
    )

    token = mint_token(sub="clerk_pl_k", email="pl_k@example.com", name="Pip")
    joiner = FakeWebSocket(
        token=token,
        incoming=[
            {
                "type": "chat",
                "body": "A passed note.",
                "audience": "characters",
                "visible_to": [str(pip.id)],
            }
        ],
    )
    await handle_connection(joiner, game_session.id, session, clerk_verifier, room)

    def chats(ws: FakeWebSocket) -> list[Any]:
        return [m for m in ws.sent if m.get("type") == "chat"]

    assert [m["body"] for m in chats(dm_ws)] == ["A passed note."]
    assert chats(other_ws) == []
    assert [m["body"] for m in chats(joiner)] == ["A passed note."]

    events = (
        (
            await session.execute(
                select(SessionEvent).where(SessionEvent.session_id == game_session.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].audience is EventAudience.characters
    assert events[0].visible_to == [str(pip.id)]


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


async def test_initiative_persists_and_replays_after_reconnect(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    _, session_id = await _member_session(session, clerk_id="dm_i", email="dm_i@example.com")
    token = mint_token(sub="dm_i", email="dm_i@example.com")
    state = {"type": "initiative", "order": ["Pip", "Goblin"], "activeIndex": 1}
    first = FakeWebSocket(token=token, incoming=[state])
    await handle_connection(first, session_id, session, clerk_verifier, SessionHub())
    echoed = next(m for m in first.sent if m["type"] == "initiative")
    assert echoed["seq"] == 1
    second = FakeWebSocket(token=token)
    # A brand new hub proves this state is coming from Postgres.
    await handle_connection(second, session_id, session, clerk_verifier, SessionHub())
    replay = next(m for m in second.sent if m["type"] == "initiative")
    assert replay == {**state, "seq": 1}


async def test_player_cannot_change_initiative(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    dm, session_id = await _member_session(session, clerk_id="dm_p", email="dm_p@example.com")
    from boor_service.db.models import Campaign, GameSession

    game = await session.get(GameSession, session_id)
    assert game is not None
    campaign = await session.get(Campaign, game.campaign_id)
    assert campaign is not None
    player = await sync_user(session, clerk_user_id="player_i", email="player_i@example.com")
    invite = await invite_player(session, campaign=campaign, email=player.email, invited_by=dm)
    await accept_invite(session, token=invite.token, user=player)
    ws = FakeWebSocket(
        token=mint_token(sub="player_i", email=player.email),
        incoming=[
            {"type": "initiative", "order": ["Cheater"], "activeIndex": 0},
        ],
    )
    await handle_connection(ws, session_id, session, clerk_verifier, SessionHub())
    assert not any(m["type"] == "initiative" for m in ws.sent)
    assert (
        await session.scalar(select(SessionEvent).where(SessionEvent.session_id == session_id))
        is None
    )


async def test_heartbeat_is_private_and_malformed_frames_do_not_break_room(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    _, session_id = await _member_session(session, clerk_id="dm_h", email="dm_h@example.com")
    room = SessionHub()
    observer = FakeWebSocket(token=None)
    room.join(session_id, observer, Presence(user_id="observer", display_name="Observer"))
    ws = FakeWebSocket(
        token=mint_token(sub="dm_h", email="dm_h@example.com"),
        incoming=[
            {"type": []},
            {"type": "event", "body": "forged AI"},
            {"type": "standin_status", "thinking": True},
            {"type": "ping"},
            {"type": "initiative", "order": ["Pip"], "activeIndex": -1},
            {"type": "initiative", "order": ["Pip"], "activeIndex": True},
            {"type": "initiative", "order": [12]},
            {"type": "chat", "body": "Still connected"},
        ],
    )
    await handle_connection(ws, session_id, session, clerk_verifier, room)
    assert any(m["type"] == "pong" for m in ws.sent)
    assert not any(
        m["type"] in ("pong", "initiative", "event", "standin_status") for m in observer.sent
    )
    assert any(m["type"] == "chat" for m in observer.sent)


def test_presence_counts_people_not_browser_tabs():
    room = SessionHub()
    session_id = uuid.uuid4()
    first, second = FakeWebSocket(token=None), FakeWebSocket(token=None)
    person = Presence(user_id="same-user", display_name="Pip")
    room.join(session_id, first, person)
    room.join(session_id, second, person)
    assert room.roster(session_id) == [person]
    room.leave(session_id, first)
    assert room.roster(session_id) == [person]


async def test_ended_room_rejects_chat_rolls_and_initiative(
    session: AsyncSession, clerk_verifier: ClerkVerifier, mint_token: TokenFactory
) -> None:
    from boor_service.db.models import GameSession
    from boor_service.db.repository import end_session, session_timeline

    user, session_id = await _member_session(session, clerk_id="ended", email="ended@example.com")
    game = await session.get(GameSession, session_id)
    assert game is not None
    await end_session(session, game_session=game)
    await session.commit()
    ws = FakeWebSocket(
        token=mint_token(sub="ended", email=user.email),
        incoming=[
            {"type": "chat", "body": "Too late"},
            {"type": "roll", "body": "20"},
            {"type": "initiative", "order": ["Late"], "activeIndex": 0},
            {"type": "ping"},
        ],
    )
    await handle_connection(ws, session_id, session, clerk_verifier, SessionHub())
    assert len([m for m in ws.sent if m["type"] == "error"]) == 3
    assert any(m["type"] == "pong" for m in ws.sent)
    assert await session_timeline(session, game_session=game) == []
