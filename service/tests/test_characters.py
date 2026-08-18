"""Tests for character persistence + the stand-in personality layer (DATA-02/04).

Runs against an ephemeral testcontainers Postgres (see ``conftest.py``) so real
constraints, cascades, and the JSONB round-trip are exercised — not a SQLite
approximation. The key invariant under test is that a persisted red line
round-trips back into the *same* pure ``check_action`` the stand-in gates on, so
the DB and the guardrail layer never drift.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.ai import (
    ActionType,
    Disposition,
    Entity,
    GameState,
    ProposedAction,
    RedLine,
    RedLineKind,
    Refused,
    check_action,
)
from boor_service.ai.standin import build_standin_context
from boor_service.character import Character as CharacterSheet
from boor_service.db.models import (
    Campaign,
    Character,
    CharacterRedLine,
    PersonalityProfile,
    RiskTolerance,
    User,
)
from boor_service.db.repository import (
    add_red_line,
    create_campaign_with_owner,
    create_character,
    red_lines_for,
    set_personality_profile,
)

UserFactory = Callable[..., Awaitable[User]]


async def _campaign(session: AsyncSession, owner: User) -> Campaign:
    return await create_campaign_with_owner(session, name="Test Table", owner=owner)


async def test_create_character_defaults(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await _campaign(session, owner)

    character = await create_character(session, campaign=campaign, name="Thorin")

    assert character.id is not None
    assert character.created_at is not None
    assert character.level == 1
    assert character.sheet == {}
    assert character.player_id is None


async def test_character_belongs_to_campaign_and_player(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    player = await make_user()
    campaign = await _campaign(session, owner)

    character = await create_character(
        session,
        campaign=campaign,
        name="Lyra",
        level=3,
        sheet={"abilities": {"dex": 16}},
        player=player,
    )

    assert character.player_id == player.id
    assert character.sheet == {"abilities": {"dex": 16}}
    # back-reference from the campaign
    fetched = await session.get(Campaign, campaign.id)
    assert fetched is not None
    await session.refresh(fetched, ["characters"])
    assert [c.id for c in fetched.characters] == [character.id]


async def test_set_personality_profile_is_an_upsert(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await _campaign(session, owner)
    character = await create_character(session, campaign=campaign, name="Vex")

    first = await set_personality_profile(
        session,
        character=character,
        persona="A wary rogue who speaks in half-truths.",
        standing_instructions="Avoid open combat; scout ahead.",
        risk_tolerance=RiskTolerance.cautious,
        traits={"quirks": ["taps dagger when nervous"]},
    )
    second = await set_personality_profile(
        session,
        character=character,
        persona="A bolder rogue now.",
        risk_tolerance=RiskTolerance.bold,
    )

    # same row updated, not a second profile
    assert second.id == first.id
    rows = (
        await session.execute(
            select(PersonalityProfile).where(
                PersonalityProfile.character_id == character.id
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].persona == "A bolder rogue now."
    assert rows[0].risk_tolerance is RiskTolerance.bold
    assert rows[0].traits == {}  # reset by the second upsert


async def test_profile_unique_per_character(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await _campaign(session, owner)
    character = await create_character(session, campaign=campaign, name="Dup")
    await set_personality_profile(session, character=character, persona="one")

    session.add(PersonalityProfile(character_id=character.id, persona="two"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_red_lines_round_trip_in_order(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await _campaign(session, owner)
    character = await create_character(session, campaign=campaign, name="Paladin")

    await add_red_line(
        session, character=character, red_line=RedLine(kind=RedLineKind.no_attacking_allies)
    )
    await add_red_line(
        session,
        character=character,
        red_line=RedLine(
            kind=RedLineKind.no_targeting_named,
            entity_ids=frozenset({"king_01"}),
            note="never harm the king",
        ),
    )
    await add_red_line(
        session,
        character=character,
        red_line=RedLine(
            kind=RedLineKind.forbid_action_types,
            action_types=frozenset({ActionType.flee, ActionType.dodge}),
            note="no cowardice",
        ),
    )

    red_lines = await red_lines_for(session, character=character)

    assert [rl.kind for rl in red_lines] == [
        RedLineKind.no_attacking_allies,
        RedLineKind.no_targeting_named,
        RedLineKind.forbid_action_types,
    ]
    assert red_lines[1].entity_ids == frozenset({"king_01"})
    assert red_lines[1].note == "never harm the king"
    assert red_lines[2].action_types == frozenset({ActionType.flee, ActionType.dodge})


async def test_persisted_red_line_feeds_check_action(
    session: AsyncSession, make_user: UserFactory
) -> None:
    """The point of the whole model: DB red lines gate the pure checker unchanged."""
    owner = await make_user()
    campaign = await _campaign(session, owner)
    character = await create_character(session, campaign=campaign, name="Guard")
    await add_red_line(
        session,
        character=character,
        red_line=RedLine(
            kind=RedLineKind.no_targeting_named,
            entity_ids=frozenset({"king_01"}),
            note="never harm the king",
        ),
    )

    red_lines = await red_lines_for(session, character=character)
    game_state = GameState(
        actor_id="guard_01",
        entities={
            "king_01": Entity(id="king_01", name="King", disposition=Disposition.ally)
        },
    )
    action = ProposedAction(
        type=ActionType.attack,
        actor_id="guard_01",
        target_ids=("king_01",),
        offensive=True,
    )

    decision = check_action(action, red_lines, game_state)

    assert isinstance(decision, Refused)
    assert "never harm the king" in decision.reason


async def test_deleting_character_cascades_to_profile_and_red_lines(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await _campaign(session, owner)
    character = await create_character(session, campaign=campaign, name="Doomed")
    await set_personality_profile(session, character=character, persona="fleeting")
    await add_red_line(
        session, character=character, red_line=RedLine(kind=RedLineKind.no_attacking_allies)
    )

    obj = await session.get(Character, character.id)
    assert obj is not None
    await session.delete(obj)
    await session.flush()

    profiles = (
        await session.execute(
            select(PersonalityProfile).where(
                PersonalityProfile.character_id == character.id
            )
        )
    ).scalars().all()
    red_lines = (
        await session.execute(
            select(CharacterRedLine).where(
                CharacterRedLine.character_id == character.id
            )
        )
    ).scalars().all()
    assert profiles == []
    assert red_lines == []


async def test_deleting_campaign_cascades_to_characters(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await _campaign(session, owner)
    await create_character(session, campaign=campaign, name="Ghost")

    obj = await session.get(Campaign, campaign.id)
    assert obj is not None
    await session.delete(obj)
    await session.flush()

    remaining = (
        await session.execute(
            select(Character).where(Character.campaign_id == campaign.id)
        )
    ).scalars().all()
    assert remaining == []


async def test_build_standin_context_from_persisted_record(
    session: AsyncSession, make_user: UserFactory
) -> None:
    """The bridge: persisted sheet + profile + red lines -> a StandInContext."""
    owner = await make_user()
    campaign = await _campaign(session, owner)
    sheet = CharacterSheet(
        name="Vex",
        level=5,
        abilities={"str": 8, "dex": 18, "con": 14, "int": 12, "wis": 13, "cha": 16},
        max_hp=38,
        skill_proficiencies=frozenset({"stealth", "perception"}),
        skill_expertise=frozenset({"stealth"}),
    )
    character = await create_character(
        session, campaign=campaign, name="Vex", level=5, sheet=sheet.to_sheet()
    )
    await set_personality_profile(
        session,
        character=character,
        persona="A sly ranger who trusts no one.",
        standing_instructions="Scout ahead; avoid melee.",
        risk_tolerance=RiskTolerance.cautious,
    )
    await add_red_line(
        session,
        character=character,
        red_line=RedLine(kind=RedLineKind.no_attacking_allies, note="never hit friends"),
    )

    game_state = GameState(actor_id="vex_01")
    context = await build_standin_context(
        session, character=character, game_state=game_state
    )

    assert context.character_name == "Vex"
    assert context.persona == "A sly ranger who trusts no one."
    assert "Scout ahead" in context.standing_instructions
    assert "cautiously" in context.standing_instructions.lower()  # risk tolerance folded in
    assert "DEX 18 (+4)" in context.character_sheet
    assert "Expertise: stealth" in context.character_sheet
    assert [rl.kind for rl in context.red_lines] == [RedLineKind.no_attacking_allies]
    assert context.game_state is game_state


async def test_build_standin_context_without_profile(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    campaign = await _campaign(session, owner)
    sheet = CharacterSheet(
        name="Mook",
        level=1,
        abilities={"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
        max_hp=8,
    )
    character = await create_character(
        session, campaign=campaign, name="Mook", sheet=sheet.to_sheet()
    )

    context = await build_standin_context(
        session, character=character, game_state=GameState(actor_id="mook_01")
    )

    assert context.persona == ""
    assert context.standing_instructions == ""
    assert context.red_lines == ()


async def test_deleting_player_nulls_character_owner(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    player = await make_user()
    campaign = await _campaign(session, owner)
    character = await create_character(
        session, campaign=campaign, name="Orphaned", player=player
    )

    obj = await session.get(User, player.id)
    assert obj is not None
    await session.delete(obj)
    await session.flush()

    await session.refresh(character)
    assert character.player_id is None
