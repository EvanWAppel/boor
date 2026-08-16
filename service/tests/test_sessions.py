"""Tests for session records and the unified timeline (DATA-03).

Runs against ephemeral Postgres (see ``conftest.py``). The timeline is one
ordered ``SessionEvent`` stream; the story log is its narrative subset.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.db.models import (
    EventKind,
    GameSession,
    SessionEvent,
    SessionStatus,
    User,
)
from boor_service.db.repository import (
    append_event,
    create_campaign_with_owner,
    create_session,
    end_session,
    story_log,
)

UserFactory = Callable[..., Awaitable[User]]


async def _campaign_with_session(
    session: AsyncSession,
    make_user: UserFactory,
    *,
    title: str | None = None,
    status: SessionStatus = SessionStatus.scheduled,
) -> GameSession:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    return await create_session(
        session, campaign=campaign, title=title, status=status
    )


async def test_create_session_defaults_to_scheduled(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user, title="Session 1")
    assert game_session.id is not None
    assert game_session.status is SessionStatus.scheduled
    assert game_session.started_at is None
    assert game_session.ended_at is None
    assert game_session.title == "Session 1"


async def test_create_active_session_stamps_started_at(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(
        session, make_user, status=SessionStatus.active
    )
    assert game_session.status is SessionStatus.active
    assert game_session.started_at is not None


async def test_append_event_assigns_incrementing_seq(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user)
    first = await append_event(session, game_session=game_session, kind=EventKind.system)
    second = await append_event(session, game_session=game_session, kind=EventKind.roll)
    third = await append_event(session, game_session=game_session, kind=EventKind.action)
    assert [first.seq, second.seq, third.seq] == [1, 2, 3]


async def test_seq_is_per_session(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    s1 = await create_session(session, campaign=campaign)
    s2 = await create_session(session, campaign=campaign)
    e1 = await append_event(session, game_session=s1, kind=EventKind.system)
    e2 = await append_event(session, game_session=s2, kind=EventKind.system)
    assert e1.seq == 1
    assert e2.seq == 1


async def test_duplicate_seq_rejected(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user)
    await append_event(session, game_session=game_session, kind=EventKind.system)
    session.add(
        SessionEvent(session_id=game_session.id, seq=1, kind=EventKind.roll)
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_event_records_actor_body_payload_and_ai_flag(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    game_session = await create_session(session, campaign=campaign)

    event = await append_event(
        session,
        game_session=game_session,
        kind=EventKind.roll,
        actor=owner,
        body="rolls to hit",
        payload={"notation": "1d20+5", "total": 18},
        ai_generated=True,
    )
    assert event.actor_user_id == owner.id
    assert event.body == "rolls to hit"
    assert event.payload == {"notation": "1d20+5", "total": 18}
    assert event.ai_generated is True


async def test_event_payload_defaults_to_empty_dict(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user)
    event = await append_event(
        session, game_session=game_session, kind=EventKind.turn, actor_label="Goblin"
    )
    assert event.payload == {}
    assert event.actor_user_id is None
    assert event.actor_label == "Goblin"
    assert event.ai_generated is False


async def test_events_relationship_ordered_by_seq(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user)
    for kind in (EventKind.system, EventKind.roll, EventKind.action):
        await append_event(session, game_session=game_session, kind=kind)

    reloaded = await session.get(GameSession, game_session.id)
    assert reloaded is not None
    await session.refresh(reloaded, ["events"])
    assert [e.seq for e in reloaded.events] == [1, 2, 3]


async def test_story_log_filters_to_narrative_kinds_in_order(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user)
    await append_event(session, game_session=game_session, kind=EventKind.system)
    await append_event(
        session, game_session=game_session, kind=EventKind.narration, body="A tavern."
    )
    await append_event(session, game_session=game_session, kind=EventKind.roll)
    await append_event(
        session, game_session=game_session, kind=EventKind.in_character, body="Hail!"
    )
    await append_event(
        session, game_session=game_session, kind=EventKind.out_of_character, body="brb"
    )

    story = await story_log(session, game_session=game_session)
    assert [e.body for e in story] == ["A tavern.", "Hail!"]


async def test_end_session_sets_status_and_timestamp(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(
        session, make_user, status=SessionStatus.active
    )
    ended = await end_session(session, game_session=game_session)
    assert ended.status is SessionStatus.ended
    assert ended.ended_at is not None


async def test_deleting_session_cascades_events(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user)
    await append_event(session, game_session=game_session, kind=EventKind.system)

    obj = await session.get(GameSession, game_session.id)
    assert obj is not None
    await session.delete(obj)
    await session.flush()

    remaining = (
        await session.execute(
            select(SessionEvent).where(SessionEvent.session_id == game_session.id)
        )
    ).scalars().all()
    assert remaining == []


async def test_deleting_campaign_cascades_sessions(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Doomed", owner=owner)
    game_session = await create_session(session, campaign=campaign)
    await append_event(session, game_session=game_session, kind=EventKind.system)

    await session.delete(campaign)
    await session.flush()

    remaining_sessions = (
        await session.execute(
            select(GameSession).where(GameSession.campaign_id == campaign.id)
        )
    ).scalars().all()
    assert remaining_sessions == []


async def test_actor_set_null_when_user_deleted(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    player = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    game_session = await create_session(session, campaign=campaign)
    event = await append_event(
        session, game_session=game_session, kind=EventKind.action, actor=player
    )
    assert event.actor_user_id == player.id

    await session.delete(player)
    await session.flush()
    await session.refresh(event)
    assert event.actor_user_id is None
