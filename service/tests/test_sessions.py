"""Tests for session records and the unified timeline (DATA-03).

Runs against ephemeral Postgres (see ``conftest.py``). The timeline is one
ordered ``SessionEvent`` stream; the story log is its narrative subset.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.db.models import (
    EventAudience,
    EventKind,
    GameSession,
    SessionEvent,
    SessionStatus,
    User,
)
from boor_service.db.repository import (
    accept_invite,
    append_event,
    create_campaign_with_owner,
    create_character,
    create_session,
    end_session,
    invite_player,
    render_timeline,
    reveal_event_to,
    session_timeline,
    sessions_for_campaign,
    story_log,
    timeline_for_character,
    timeline_for_viewer,
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
    return await create_session(session, campaign=campaign, title=title, status=status)


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
    game_session = await _campaign_with_session(session, make_user, status=SessionStatus.active)
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


async def test_seq_is_per_session(session: AsyncSession, make_user: UserFactory) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    s1 = await create_session(session, campaign=campaign)
    s2 = await create_session(session, campaign=campaign)
    e1 = await append_event(session, game_session=s1, kind=EventKind.system)
    e2 = await append_event(session, game_session=s2, kind=EventKind.system)
    assert e1.seq == 1
    assert e2.seq == 1


async def test_duplicate_seq_rejected(session: AsyncSession, make_user: UserFactory) -> None:
    game_session = await _campaign_with_session(session, make_user)
    await append_event(session, game_session=game_session, kind=EventKind.system)
    session.add(SessionEvent(session_id=game_session.id, seq=1, kind=EventKind.roll))
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


async def test_session_timeline_returns_every_kind_in_order(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user)
    await append_event(session, game_session=game_session, kind=EventKind.system)
    await append_event(session, game_session=game_session, kind=EventKind.roll, body="1d20")
    await append_event(
        session, game_session=game_session, kind=EventKind.in_character, body="Hail!"
    )
    await append_event(
        session, game_session=game_session, kind=EventKind.out_of_character, body="brb"
    )

    timeline = await session_timeline(session, game_session=game_session)
    # unlike story_log, the full timeline keeps system/roll/ooc too
    assert [e.kind for e in timeline] == [
        EventKind.system,
        EventKind.roll,
        EventKind.in_character,
        EventKind.out_of_character,
    ]


async def test_sessions_for_campaign_newest_first(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    first = await create_session(session, campaign=campaign, title="One")
    second = await create_session(session, campaign=campaign, title="Two")
    # Postgres now() is transaction-fixed, so same-tx rows would tie; give them
    # distinct created_at to assert the ordering deterministically (in production
    # each session opens in its own request, so real created_at values differ).
    first.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    second.created_at = datetime(2026, 1, 2, tzinfo=UTC)
    await session.flush()

    listed = await sessions_for_campaign(session, campaign_id=campaign.id)
    assert [s.id for s in listed] == [second.id, first.id]


async def test_sessions_for_campaign_is_scoped_to_the_campaign(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    mine = await create_campaign_with_owner(session, name="Mine", owner=owner)
    theirs = await create_campaign_with_owner(session, name="Theirs", owner=owner)
    await create_session(session, campaign=mine)
    await create_session(session, campaign=theirs)

    listed = await sessions_for_campaign(session, campaign_id=mine.id)
    assert len(listed) == 1
    assert listed[0].campaign_id == mine.id


async def test_end_session_sets_status_and_timestamp(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user, status=SessionStatus.active)
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
        (
            await session.execute(
                select(SessionEvent).where(SessionEvent.session_id == game_session.id)
            )
        )
        .scalars()
        .all()
    )
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
        (await session.execute(select(GameSession).where(GameSession.campaign_id == campaign.id)))
        .scalars()
        .all()
    )
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


# --- DATA-07: per-character knowledge scoping --------------------------------


async def test_append_event_defaults_to_table_audience(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user)
    event = await append_event(
        session, game_session=game_session, kind=EventKind.narration, body="A tavern."
    )
    assert event.audience is EventAudience.table
    assert event.visible_to == []


async def test_append_event_characters_audience_requires_ids(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user)
    with pytest.raises(ValueError, match="at least one character id"):
        await append_event(
            session,
            game_session=game_session,
            kind=EventKind.in_character,
            audience=EventAudience.characters,
        )


async def test_timeline_for_character_hides_other_pcs_secrets(
    session: AsyncSession, make_user: UserFactory
) -> None:
    """Primer §4.2: the paladin's stand-in must not see the rogue's private bribe."""
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    game_session = await create_session(session, campaign=campaign)
    paladin = await create_character(session, campaign=campaign, name="Paladin")
    rogue = await create_character(session, campaign=campaign, name="Rogue")

    await append_event(
        session,
        game_session=game_session,
        kind=EventKind.narration,
        body="The duke greets the party.",
    )
    bribe = await append_event(
        session,
        game_session=game_session,
        kind=EventKind.in_character,
        actor_label="Rogue",
        body="I'll take the gold. The paladin hears nothing.",
        audience=EventAudience.characters,
        visible_to=[rogue.id],
    )
    await append_event(
        session,
        game_session=game_session,
        kind=EventKind.system,
        body="DM note: the duke is lying.",
        audience=EventAudience.dm,
    )

    paladin_view = await timeline_for_character(
        session, game_session=game_session, character=paladin
    )
    rogue_view = await timeline_for_character(session, game_session=game_session, character=rogue)
    full = await session_timeline(session, game_session=game_session)

    assert [e.body for e in paladin_view] == ["The duke greets the party."]
    assert [e.body for e in rogue_view] == [
        "The duke greets the party.",
        "I'll take the gold. The paladin hears nothing.",
    ]
    assert len(full) == 3
    assert bribe.audience is EventAudience.characters


async def test_timeline_for_viewer_dm_sees_all_player_does_not(
    session: AsyncSession, make_user: UserFactory
) -> None:
    dm = await make_user()
    player = await make_user(email="player@example.com")
    campaign = await create_campaign_with_owner(session, name="Camp", owner=dm)
    invite = await invite_player(session, campaign=campaign, email=player.email, invited_by=dm)
    await accept_invite(session, token=invite.token, user=player)
    game_session = await create_session(session, campaign=campaign)
    hero = await create_character(session, campaign=campaign, name="Hero", player=player)

    await append_event(session, game_session=game_session, kind=EventKind.narration, body="Public.")
    await append_event(
        session,
        game_session=game_session,
        kind=EventKind.in_character,
        body="Whisper.",
        audience=EventAudience.characters,
        visible_to=[hero.id],
    )
    await append_event(
        session,
        game_session=game_session,
        kind=EventKind.system,
        body="DM only.",
        audience=EventAudience.dm,
    )

    dm_view = await timeline_for_viewer(session, game_session=game_session, viewer=dm)
    player_view = await timeline_for_viewer(session, game_session=game_session, viewer=player)
    assert [e.body for e in dm_view] == ["Public.", "Whisper.", "DM only."]
    assert [e.body for e in player_view] == ["Public.", "Whisper."]


async def test_reveal_event_to_grants_knowledge(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    game_session = await create_session(session, campaign=campaign)
    paladin = await create_character(session, campaign=campaign, name="Paladin")
    rogue = await create_character(session, campaign=campaign, name="Rogue")

    secret = await append_event(
        session,
        game_session=game_session,
        kind=EventKind.in_character,
        body="A passed note.",
        audience=EventAudience.characters,
        visible_to=[rogue.id],
    )
    assert [
        e.body
        for e in await timeline_for_character(session, game_session=game_session, character=paladin)
    ] == []

    await reveal_event_to(session, event=secret, character=paladin)
    assert str(paladin.id) in secret.visible_to
    assert [
        e.body
        for e in await timeline_for_character(session, game_session=game_session, character=paladin)
    ] == ["A passed note."]


async def test_reveal_promotes_a_dm_note_to_a_character_whisper(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Camp", owner=owner)
    game_session = await create_session(session, campaign=campaign)
    hero = await create_character(session, campaign=campaign, name="Hero")
    note = await append_event(
        session,
        game_session=game_session,
        kind=EventKind.system,
        body="You notice the sigil.",
        audience=EventAudience.dm,
    )
    await reveal_event_to(session, event=note, character=hero)
    assert note.audience is EventAudience.characters
    assert note.visible_to == [str(hero.id)]


async def test_render_timeline_is_prompt_ready(
    session: AsyncSession, make_user: UserFactory
) -> None:
    game_session = await _campaign_with_session(session, make_user)
    assert render_timeline([]) == "(nothing has happened yet this session)"
    await append_event(
        session,
        game_session=game_session,
        kind=EventKind.in_character,
        actor_label="Thora",
        body="I kick the door.",
        ai_generated=True,
    )
    text = render_timeline(await session_timeline(session, game_session=game_session))
    assert text == "1. [AI] Thora: I kick the door."


async def test_concurrent_speakers_get_distinct_sequence_numbers(session, make_user):
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Concurrent table", owner=owner)
    game = await create_session(session, campaign=campaign)
    await session.commit()
    maker = async_sessionmaker(session.bind, expire_on_commit=False)

    async def speak(text):
        async with maker() as connection:
            event = await append_event(
                connection,
                game_session=game,
                kind=EventKind.in_character,
                body=text,
            )
            await connection.commit()
            return event.seq

    seqs = await asyncio.wait_for(asyncio.gather(*(speak(str(i)) for i in range(8))), 10)
    assert sorted(seqs) == list(range(1, 9))
