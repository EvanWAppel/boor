"""Local-dev seed data (DATA-06): a believable table, persisted.

    uv run python -m boor_service.db.seed

Populates a fresh database with one demo campaign and the full graph the rest of
the stack expects: a DM, two players joined via the real invite -> accept flow,
their characters (with lossless 5e sheets), each character's stand-in personality
profile, and its standing red lines. A scheduled session is created so the
timeline has somewhere to land.

Everything routes through :mod:`boor_service.db.repository`, so the seed doubles
as a living integration example of the data layer — and the world it builds is the
same Thora/Lyra encounter the in-memory ``boor_service.demo`` plays, so a
developer can point the app at a DB that already has a stand-in-ready character.

Run against the ``DATABASE_URL`` the app uses. It is **not** idempotent: it appends
a new campaign each run (fine for a scratch dev DB).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.ai.guardrails import RedLine, RedLineKind
from boor_service.character import Character as CharacterSheet
from boor_service.db.models import Campaign, Character, GameSession, RiskTolerance, User
from boor_service.db.repository import (
    accept_invite,
    add_red_line,
    create_campaign_with_owner,
    create_character,
    create_session,
    invite_player,
    set_personality_profile,
)
from boor_service.db.session import get_sessionmaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeedResult:
    """Handles to the seeded graph, returned so callers/tests can assert on it."""

    campaign: Campaign
    dm: User
    players: tuple[User, ...]
    characters: tuple[Character, ...]
    session: GameSession


def _thora_sheet() -> dict:
    """A level-5 protector-fighter, as a persisted sheet blob."""
    return CharacterSheet(
        name="Thora",
        level=5,
        abilities={"str": 18, "dex": 12, "con": 16, "int": 8, "wis": 13, "cha": 10},
        max_hp=44,
        skill_proficiencies=frozenset({"athletics", "intimidation", "perception"}),
        save_proficiencies=frozenset({"str", "con"}),
        base_armor_class=18,
    ).to_sheet()


def _lyra_sheet() -> dict:
    """A level-5 cleric, as a persisted sheet blob."""
    return CharacterSheet(
        name="Lyra",
        level=5,
        abilities={"str": 10, "dex": 12, "con": 14, "int": 11, "wis": 18, "cha": 13},
        max_hp=33,
        skill_proficiencies=frozenset({"medicine", "insight", "religion", "perception"}),
        save_proficiencies=frozenset({"wis", "cha"}),
        base_armor_class=16,
    ).to_sheet()


async def _add_player(
    session: AsyncSession, *, campaign: Campaign, dm: User, n: int
) -> User:
    """Create a player and join them to the campaign via the real invite flow."""
    email = f"player{n}@example.com"
    player = User(clerk_user_id=f"seed_player_{n}", email=email, display_name=f"Player {n}")
    session.add(player)
    await session.flush()
    invite = await invite_player(session, campaign=campaign, email=email, invited_by=dm)
    await accept_invite(session, token=invite.token, user=player)
    return player


async def seed_demo(session: AsyncSession) -> SeedResult:
    """Seed one demo campaign with two stand-in-ready characters and a session."""
    dm = User(clerk_user_id="seed_dm", email="dm@example.com", display_name="The DM")
    session.add(dm)
    await session.flush()

    campaign = await create_campaign_with_owner(session, name="The Shrine of the Hag", owner=dm)
    player1 = await _add_player(session, campaign=campaign, dm=dm, n=1)
    player2 = await _add_player(session, campaign=campaign, dm=dm, n=2)

    thora = await create_character(
        session, campaign=campaign, name="Thora", level=5, sheet=_thora_sheet(), player=player1
    )
    await set_personality_profile(
        session,
        character=thora,
        persona=(
            "Blunt, brave, fiercely protective of her companions. Words when safe, "
            "steel when not."
        ),
        standing_instructions="Protect the healer. Don't flee a winnable fight.",
        risk_tolerance=RiskTolerance.bold,
        traits={"goals": ["keep the party alive"], "quirks": ["never draws first"]},
    )
    await add_red_line(
        session,
        character=thora,
        red_line=RedLine(kind=RedLineKind.no_attacking_allies, note="never attack a party member"),
    )

    lyra = await create_character(
        session, campaign=campaign, name="Lyra", level=5, sheet=_lyra_sheet(), player=player2
    )
    await set_personality_profile(
        session,
        character=lyra,
        persona="Gentle and watchful; heals first, judges later. Speaks softly, means it.",
        standing_instructions="Keep everyone standing. Avoid melee; hang back and support.",
        risk_tolerance=RiskTolerance.cautious,
        traits={"goals": ["mend the wounded"], "relationships": {"Thora": "trusts with her life"}},
    )
    await add_red_line(
        session,
        character=lyra,
        red_line=RedLine(
            kind=RedLineKind.no_attacking_the_helpless, note="never strike a downed creature"
        ),
    )

    game_session = await create_session(session, campaign=campaign, title="Session 1 — The Shrine")

    logger.info(
        "seeded campaign %s: %s + 2 players, characters Thora/Lyra, session %s",
        campaign.id,
        dm.email,
        game_session.id,
    )
    return SeedResult(
        campaign=campaign,
        dm=dm,
        players=(player1, player2),
        characters=(thora, lyra),
        session=game_session,
    )


async def _main() -> None:
    maker = get_sessionmaker()
    async with maker() as session:
        result = await seed_demo(session)
        await session.commit()
    print(
        f"Seeded campaign {result.campaign.id!s} "
        f"({len(result.characters)} characters, {len(result.players)} players)."
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(_main())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
