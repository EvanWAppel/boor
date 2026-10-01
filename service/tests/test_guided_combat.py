"""Deterministic practice mechanics plus authenticated, persisted turns."""

import copy
import uuid

import pytest

from boor_service import guided_combat as combat
from boor_service import guided_scenes
from boor_service.character import Character
from tests.test_guided import command
from tests.test_guided_conversation import open_conversation
from tests.test_session_api import _auth


@pytest.fixture(autouse=True)
def _legacy_version(monkeypatch):
    monkeypatch.setattr(guided_scenes, "VERSION", 4)


class Sequence:
    def __init__(self, values):
        self.values = iter(values)

    def randint(self, a, b):
        value = next(self.values)
        assert a <= value <= b
        return value


class Low:
    def randint(self, a, b):
        assert a <= b
        return a


def sheet(name="Hero", hp=10):
    return Character(name, 1, dict(str=16, dex=12, con=12, int=10, wis=10, cha=10), hp)


def practice():
    return combat.start_encounter([("hero", "character", sheet())], "river", rng=Sequence([20, 1]))


def test_critical_hit_wins_and_does_not_mutate_sheet():
    hero = sheet()
    original = hero.to_sheet()
    encounter = combat.start_encounter([("hero", "character", hero)], "town", rng=Sequence([20, 1]))
    combat.take_action(encounter, "hero", "strike", rng=Sequence([20, 6, 6]))
    assert encounter["outcome"]["reason"] == "victory"
    assert encounter["fighters"]["mara"]["hp"] == 0
    assert "Critical hit!" in encounter["messages"][0]
    assert hero.to_sheet() == original and hero.combatant.current_hp == hero.max_hp
    assert combat.current_actor(encounter) is None


def test_dodge_disadvantage_expires_and_natural_one_misses():
    encounter = practice()
    combat.take_action(encounter, "hero", "dodge", rng=Sequence([20, 1]))
    assert encounter["fighters"]["hero"]["hp"] == 10
    assert not encounter["fighters"]["hero"]["dodging"]
    assert "disadvantage" in encounter["messages"][1]
    # Hero misses; Mara hits normally on the next turn and does 2 damage.
    combat.take_action(encounter, "hero", "strike", rng=Sequence([1, 15, 1]))
    assert encounter["fighters"]["hero"]["hp"] == 8
    assert encounter["fighters"]["mara"]["hp"] == 12


def test_round_limit_and_withdrawal_are_terminal():
    encounter = practice()
    for _ in range(5):
        combat.take_action(encounter, "hero", "dodge", rng=Low())
    assert encounter["outcome"]["reason"] == "limit"
    with pytest.raises(ValueError):
        combat.take_action(encounter, "hero", "strike")
    encounter = practice()
    combat.take_action(encounter, "hero", "withdraw")
    assert encounter["outcome"]["reason"] == "withdrawn"
    assert encounter["fighters"]["hero"]["hp"] == 10


def test_enemy_first_can_end_bout_safely():
    encounter = combat.start_encounter(
        [("hero", "character", sheet(hp=1))], "town", rng=Sequence([1, 20, 20, 4, 4])
    )
    assert encounter["outcome"]["reason"] == "defeat"
    assert encounter["fighters"]["hero"]["hp"] == 0


def test_inactive_characters_are_skipped_and_not_targeted():
    encounter = combat.start_encounter(
        [("first", "one", sheet("First")), ("second", "two", sheet("Second"))],
        "town",
        rng=Sequence([20, 10, 1]),
    )
    before = copy.deepcopy(encounter)
    with pytest.raises(ValueError):
        combat.take_action(encounter, "second", "strike")
    assert encounter == before
    combat.take_action(encounter, "first", "withdraw")
    assert combat.current_actor(encounter) == "second"
    combat.take_action(encounter, "second", "dodge", rng=Low())
    assert combat.current_actor(encounter) == "second"
    assert "attacks Second" in encounter["messages"][1]
    combat.stop_encounter(encounter)
    assert encounter["outcome"]["reason"] == "withdrawn"


BATTLE_TEXT = {
    "victory": "The foes are driven off.",
    "defeat": "You are overwhelmed but pulled to safety.",
    "withdrawn": "You break off and slip away.",
    "limit": "The skirmish breaks up.",
}


def battle(party, *, enemies, rng):
    return combat.start_battle(
        party, enemies, intro="A fight breaks out.", descriptions=BATTLE_TEXT, rng=rng
    )


def test_battle_requires_and_validates_a_target():
    enemies = [
        combat.Enemy("wolf1", "Grey wolf", hp=6, ac=11, bonus=3, damage="1d4"),
        combat.Enemy("wolf2", "Lean wolf", hp=6, ac=11, bonus=3, damage="1d4"),
    ]
    # Hero rolls initiative first (players before enemies), then the two wolves roll.
    encounter = battle([("hero", "c", sheet())], enemies=enemies, rng=Sequence([15, 1, 1]))
    assert combat.current_actor(encounter) == "hero"
    assert set(combat.enemy_targets(encounter)) == {"wolf1", "wolf2"}
    with pytest.raises(ValueError):
        combat.take_action(encounter, "hero", "strike", rng=Sequence([20, 3]))
    with pytest.raises(ValueError):
        combat.take_action(encounter, "hero", "strike", target="mara", rng=Sequence([20, 3]))


def test_battle_victory_needs_all_enemies_down():
    enemies = [
        combat.Enemy("wolf1", "Grey wolf", hp=6, ac=1, bonus=-5, damage="1d4"),
        combat.Enemy("wolf2", "Lean wolf", hp=6, ac=1, bonus=-5, damage="1d4"),
    ]
    encounter = battle([("hero", "c", sheet())], enemies=enemies, rng=Sequence([15, 1, 1]))
    # Hero crits wolf1 (20 + 6 + 6); the surviving wolf2 then misses on its -5 attack (roll 2).
    combat.take_action(encounter, "hero", "strike", target="wolf1", rng=Sequence([20, 6, 6, 2]))
    assert encounter["fighters"]["wolf1"]["hp"] == 0
    # One enemy still stands, so the fight continues (wolves miss on -5 to hit).
    assert encounter["outcome"] is None
    assert combat.enemy_targets(encounter) == ["wolf2"]
    # A lone remaining enemy no longer needs an explicit target.
    combat.take_action(encounter, "hero", "strike", rng=Sequence([20, 6, 6]))
    assert encounter["outcome"]["reason"] == "victory"
    assert encounter["outcome"]["body"] == BATTLE_TEXT["victory"]


def test_battle_lines_do_not_mention_practice():
    enemies = [combat.Enemy("wolf1", "Grey wolf", hp=6, ac=1, bonus=10, damage="1d4")]
    encounter = battle([("hero", "c", sheet())], enemies=enemies, rng=Sequence([15, 1]))
    combat.take_action(encounter, "hero", "strike", rng=Sequence([20, 6, 6]))
    joined = " ".join(encounter["messages"])
    assert "practice" not in joined.lower()
    assert "HP lost" in joined


def test_pre_migration_sparring_bout_finishes_without_keyerror():
    # A v4 bout persisted before this change has no descriptions/labels keys.
    encounter = combat.start_encounter([("hero", "c", sheet())], "town", rng=Sequence([20, 1]))
    del encounter["labels"], encounter["descriptions"]
    combat.take_action(encounter, "hero", "strike", rng=Sequence([20, 6, 6]))
    assert encounter["outcome"]["reason"] == "victory"
    assert "Everyone recovers after practice" in encounter["outcome"]["body"]
    assert "practice HP lost" in " ".join(encounter["messages"])


def test_pre_migration_bout_stop_keeps_sparring_wording():
    encounter = combat.start_encounter([("hero", "c", sheet())], "river", rng=Sequence([20, 1]))
    del encounter["labels"], encounter["descriptions"]
    combat.stop_encounter(encounter)
    assert encounter["outcome"]["reason"] == "withdrawn"
    assert encounter["messages"][0] == "The host stops the practice bout for the party."


async def open_practice(client, mint_token):
    path, host, player, state = await open_conversation(client, mint_token, host_plays=True)
    for action, extra in [
        ("ask", {"topic": "road"}),
        ("choose", {"choice": "town"}),
        ("continue", {}),
    ]:
        response = await client.post(
            path + "/guided", headers=_auth(host), json=command(action, state["revision"], **extra)
        )
        assert response.status_code == 200, response.text
        state = response.json()["state"]
    return path, host, player, state


async def test_combat_authority_retries_replay_and_end(auth_client, mint_token):
    path, host, player, state = await open_practice(auth_client, mint_token)
    assert state["phase"] == "combat"
    ids = {
        (await auth_client.get("/me", headers=_auth(token))).json()["id"]: token
        for token in (host, player)
    }
    active = combat.current_actor(state["encounter"])
    token = ids[active]
    other = next(t for uid, t in ids.items() if uid != active)
    request = command("combat_action", state["revision"], move="dodge")
    assert (
        await auth_client.post(path + "/guided", headers=_auth(other), json=request)
    ).status_code == 403
    forged = {**request, "damage": 999}
    assert (
        await auth_client.post(path + "/guided", headers=_auth(token), json=forged)
    ).status_code == 422
    result = await auth_client.post(path + "/guided", headers=_auth(token), json=request)
    assert result.status_code == 200
    retry = await auth_client.post(path + "/guided", headers=_auth(token), json=request)
    assert retry.json() == result.json()
    replay = (await auth_client.get(path + "/guided", headers=_auth(other))).json()["state"]
    assert replay["encounter"] == result.json()["state"]["encounter"]
    stop = command("stop_practice", replay["revision"])
    assert (
        await auth_client.post(path + "/guided", headers=_auth(player), json=stop)
    ).status_code == 403
    stopped = await auth_client.post(path + "/guided", headers=_auth(host), json=stop)
    assert stopped.status_code == 200
    assert stopped.json()["state"]["phase"] == "combat_outcome"
    assert (await auth_client.post(path + "/end", headers=_auth(host))).status_code == 200
    assert (
        await auth_client.post(path + "/guided", headers=_auth(token), json=request)
    ).status_code == 409


async def test_version_three_still_finishes_without_combat(auth_client, mint_token, session):
    from boor_service.db.models import EventKind, GameSession
    from boor_service.db.repository import append_event
    from tests.test_guided import setup

    path, host, _ = await setup(auth_client, mint_token)
    game = await session.get(GameSession, uuid.UUID(path.split("/")[-1]))
    assert game is not None
    await append_event(
        session,
        game_session=game,
        kind=EventKind.narration,
        payload={
            "type": "guided_cart_v3",
            "state": {"version": 3, "revision": 1, "phase": "decision", "participants": {}},
        },
    )
    await session.commit()
    result = await auth_client.post(
        path + "/guided", headers=_auth(host), json=command("continue", 1)
    )
    assert result.status_code == 200
    assert result.json()["state"]["phase"] == "complete"
    assert not result.json()["state"].get("encounter")


def test_practice_preserves_character_damage_defenses():
    hero = sheet()
    hero.resistances = frozenset({"bludgeoning"})
    encounter = combat.start_encounter([("hero", "character", hero)], "town", rng=Sequence([20, 1]))
    combat.take_action(encounter, "hero", "strike", rng=Sequence([1, 15, 4]))
    # Five bludgeoning damage is halved and rounded down.
    assert encounter["fighters"]["hero"]["hp"] == 8


async def test_competing_turn_commands_apply_only_once(auth_client, mint_token, session):
    import asyncio

    from fastapi import BackgroundTasks, HTTPException
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from boor_service import guided
    from boor_service.db.models import GameSession, User

    path, host, player, state = await open_practice(auth_client, mint_token)
    ids = {(await auth_client.get("/me", headers=_auth(t))).json()["id"]: t for t in (host, player)}
    active = combat.current_actor(state["encounter"])
    assert active in ids
    await session.commit()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    game_id = uuid.UUID(path.split("/")[-1])

    async def move(action):
        async with factory() as db:
            game = await db.get(GameSession, game_id)
            user = await db.get(User, uuid.UUID(active))
            assert game is not None and user is not None
            try:
                await guided.command_guided(
                    guided.Command(**command("combat_action", state["revision"], move=action)),
                    game,
                    user,
                    db,
                    BackgroundTasks(),
                    factory,
                )
                return 200
            except HTTPException as exc:
                await db.rollback()
                return exc.status_code

    assert sorted(await asyncio.gather(move("dodge"), move("withdraw"))) == [200, 409]
    async with factory() as db:
        recovered = await guided.latest_state(db, game_id)
        assert recovered is not None
        assert recovered["revision"] == state["revision"] + 1
