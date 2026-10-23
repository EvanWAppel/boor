"""Guided-play gap tests (GUIDED-PLAY-PLAN "Tests and success measures").

The happy paths live in ``test_guided_adventure.py``. These cover the edges the
v5 scene graph had no test for: two accounts racing on one revision, an AI-guide
decision landing after the session ended or after the scene moved on, and a
reconnect (fresh GET) mid-check and mid-fight.
"""

import asyncio
import uuid

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker

from boor_service import guided, guided_scenes
from boor_service.ai.adjudicator import Adjudication
from boor_service.db.models import GameSession, User
from tests.test_guided import command, setup
from tests.test_guided_adventure import _to_battle, begin, fixed_check
from tests.test_session_api import _auth


async def _me(client, token):
    return (await client.get("/me", headers=_auth(token))).json()["id"]


async def _read(client, path, token):
    return (await client.get(path + "/guided", headers=_auth(token))).json()["state"]


async def _two_player_party(client, mint_token):
    """A v5 run where both accounts play a character (host: scholar, player: guardian)."""
    path, host, player = await setup(client, mint_token)

    async def act(token, action, rev, **extra):
        r = await client.post(
            path + "/guided", headers=_auth(token), json=command(action, rev, **extra)
        )
        assert r.status_code == 200, r.text
        return r.json()["state"]

    state = await act(host, "start", 0)
    state = await act(player, "select", state["revision"], pregen="guardian")
    state = await act(player, "ready", state["revision"])
    state = await act(host, "select", state["revision"], pregen="scholar")
    state = await act(host, "ready", state["revision"])
    state = await act(host, "begin", state["revision"])
    assert state["version"] == 5 and state["scene"] == "cart" and len(state["participants"]) == 2
    return path, host, player, state, act


async def _race(session, path, entries):
    """Run ``(user_id, Command kwargs)`` entries concurrently, each in its own DB session.

    Returns each entry's outcome (200 or the HTTP error status) in input order.
    """
    await session.commit()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    game_id = uuid.UUID(path.split("/")[-1])

    async def run(user_id, body):
        async with factory() as db:
            game = await db.get(GameSession, game_id)
            user = await db.get(User, uuid.UUID(user_id))
            assert game is not None and user is not None
            try:
                await guided.command_guided(
                    guided.Command(**body), game, user, db, BackgroundTasks(), factory
                )
                return 200
            except HTTPException as exc:
                await db.rollback()
                return exc.status_code

    return await asyncio.gather(*(run(uid, body) for uid, body in entries))


async def test_two_accounts_racing_for_one_check_get_one_winner(
    auth_client, mint_token, session, monkeypatch
):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, _act = await _two_player_party(auth_client, mint_token)
    host_id, player_id = await _me(auth_client, host), await _me(auth_client, player)
    rev = state["revision"]
    outcomes = await _race(
        session,
        path,
        [
            (host_id, command("approach", rev, approach="leverage")),
            (player_id, command("approach", rev, approach="lift")),
        ],
    )
    assert sorted(outcomes) == [200, 409]
    after = await _read(auth_client, path, host)
    # Exactly one command landed: one revision bump, one pending check, owned by the winner.
    assert after["revision"] == rev + 1 and after["phase"] == "check"
    winner = host_id if outcomes[0] == 200 else player_id
    assert after["pending"]["user_id"] == winner
    log = (await auth_client.get(path + "/log", headers=_auth(host))).json()
    narration = [e for e in log if e["kind"] == "narration"]
    approaches = [e for e in narration if e["payload"]["command"]["action"] == "approach"]
    assert len(approaches) == 1


async def test_roll_racing_the_hosts_cancel_settles_one_way(
    auth_client, mint_token, session, monkeypatch
):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await _two_player_party(auth_client, mint_token)
    state = await act(player, "approach", state["revision"], approach="lift")
    rev = state["revision"]
    host_id, player_id = await _me(auth_client, host), await _me(auth_client, player)
    outcomes = await _race(
        session, path, [(player_id, command("roll", rev)), (host_id, command("cancel", rev))]
    )
    assert sorted(outcomes) == [200, 409]
    after = await _read(auth_client, path, host)
    assert after["revision"] == rev + 1 and after["pending"] is None
    if outcomes[0] == 200:  # the roll won: a resolved result, nothing reopened
        assert after["phase"] == "outcome" and after["result"]["success"] is True
    else:  # the cancel won: the action is open again and no die was rolled
        assert after["phase"] == "ready" and after["result"] is None


async def test_ai_decision_after_the_session_ended_is_dropped(
    auth_client, mint_token, fake_adjudicator
):
    path, host, player, state, act = await begin(auth_client, mint_token)

    async def host_ends_session():
        r = await auth_client.post(path + "/end", headers=_auth(host))
        assert r.status_code == 200, r.text

    fake_adjudicator.before = host_ends_session
    fake_adjudicator.result = Adjudication(approach="lift", reason="Fits.")
    proposed = await act(player, "propose", state["revision"], text="Shoulder the wheel")
    final = await _read(auth_client, path, host)
    # Nothing was written after the end: the last snapshot is the propose itself.
    assert final["revision"] == proposed["revision"]
    assert final["pending"] is None and final["phase"] == "ready"
    log = (await auth_client.get(path + "/log", headers=_auth(host))).json()
    assert not [e for e in log if e.get("actor_label") == "AI guide"]


async def test_ai_decision_after_the_scene_moved_on_is_dropped(
    auth_client, mint_token, monkeypatch, fake_adjudicator
):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    moved: dict = {}

    async def table_moves_on():
        # While the model thinks, the host answers, the player rolls, and the host
        # continues into the Mara conversation.
        rev = state["revision"] + 1
        s = await act(host, "accept_proposal", rev, approach="leverage")
        s = await act(player, "roll", s["revision"])
        moved.update(await act(host, "continue", s["revision"]))

    fake_adjudicator.before = table_moves_on
    fake_adjudicator.result = Adjudication(approach="lift", reason="Fits.")
    await act(player, "propose", state["revision"], text="Use a plank")
    final = await _read(auth_client, path, host)
    assert moved["scene"] == "mara"
    # The stale decision did not rewind or alter the new scene.
    assert final == moved
    log = (await auth_client.get(path + "/log", headers=_auth(host))).json()
    assert not [e for e in log if e.get("actor_label") == "AI guide"]


async def test_reconnect_mid_check_recovers_the_pending_roll(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await _two_player_party(auth_client, mint_token)
    pending = await act(player, "approach", state["revision"], approach="lift")
    # A refresh (fresh GET) from either account sees the same pending roll and owner.
    for token in (host, player):
        assert await _read(auth_client, path, token) == pending
    snapshot = await _read(auth_client, path, host)
    # Only the owner can roll it, at the revision the reconnecting client was handed.
    r = await auth_client.post(
        path + "/guided", headers=_auth(host), json=command("roll", snapshot["revision"])
    )
    assert r.status_code == 403
    rolled = await act(player, "roll", snapshot["revision"])
    assert rolled["result"]["success"] is True and rolled["pending"] is None


async def test_reconnect_mid_fight_recovers_the_turn(auth_client, mint_token, monkeypatch):
    path, host, player, state, act = await _to_battle(auth_client, mint_token, monkeypatch)
    # One strike in: a live fight with one enemy down and the turn back on the player.
    state = await act(player, "combat_action", state["revision"], move="strike", target="tough1")
    assert state["phase"] == "combat"
    snapshot = await _read(auth_client, path, host)
    assert snapshot == state
    assert snapshot["encounter"]["fighters"]["tough1"]["hp"] == 0
    # The reconnected client can carry on from the recovered revision and turn.
    done = await act(player, "combat_action", snapshot["revision"], move="strike", target="tough2")
    assert done["phase"] == "combat_outcome"
    assert done["encounter"]["outcome"]["reason"] == "victory"
