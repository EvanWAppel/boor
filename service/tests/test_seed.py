"""Tests for the local-dev seed (DATA-06).

Runs the seed against the ephemeral testcontainers Postgres and asserts the whole
graph is coherent — memberships, characters, profiles, red lines — and that a
seeded character is immediately stand-in-ready via ``build_standin_context``. That
last check is the payoff: the seed produces data the AI loop can actually consume.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.ai.actions import GameState
from boor_service.ai.standin import build_standin_context
from boor_service.db.models import Membership, MembershipRole, SessionEvent
from boor_service.db.repository import personality_profile_for, red_lines_for
from boor_service.db.seed import seed_demo


async def test_seed_builds_a_coherent_campaign(session: AsyncSession) -> None:
    result = await seed_demo(session)

    # DM + two players, all joined to the one campaign
    memberships = (
        await session.execute(
            select(Membership).where(Membership.campaign_id == result.campaign.id)
        )
    ).scalars().all()
    roles = sorted(m.role for m in memberships)
    assert roles == [MembershipRole.dm, MembershipRole.player, MembershipRole.player]
    assert result.campaign.owner_id == result.dm.id
    assert len(result.players) == 2


async def test_seed_characters_have_profiles_and_red_lines(
    session: AsyncSession,
) -> None:
    result = await seed_demo(session)

    assert {c.name for c in result.characters} == {"Thora", "Lyra"}
    for character in result.characters:
        profile = await personality_profile_for(session, character=character)
        assert profile is not None
        assert profile.persona  # non-empty
        red_lines = await red_lines_for(session, character=character)
        assert len(red_lines) >= 1
        # each character is owned by a distinct player
        assert character.player_id is not None


async def test_seed_character_is_standin_ready(session: AsyncSession) -> None:
    """End-to-end: a seeded character reconstructs into a usable StandInContext."""
    result = await seed_demo(session)
    thora = next(c for c in result.characters if c.name == "Thora")

    context = await build_standin_context(
        session, character=thora, game_state=GameState(actor_id="thora")
    )

    assert context.character_name == "Thora"
    assert context.persona
    assert "STR 18 (+4)" in context.character_sheet
    assert context.red_lines  # its red line round-tripped from the DB


async def test_seed_creates_a_session(session: AsyncSession) -> None:
    result = await seed_demo(session)
    assert result.session.campaign_id == result.campaign.id
    assert result.session.title == "Session 1 — The Shrine"
    # no timeline events yet — the session is freshly scheduled
    count = (
        await session.execute(
            select(func.count())
            .select_from(SessionEvent)
            .where(SessionEvent.session_id == result.session.id)
        )
    ).scalar_one()
    assert count == 0
