"""Auth, revision, idempotency and persisted outcomes for the authored tutorial."""

import uuid

import pytest

from boor_service import guided, guided_scenes
from boor_service.mechanics import ability_check
from tests.test_session_api import _auth, _campaign_with_player


@pytest.fixture(autouse=True)
def _legacy_version(monkeypatch):
    """These suites are the v1-v4 regression guard; pin fresh runs to the legacy v4."""
    monkeypatch.setattr(guided_scenes, "VERSION", 4)


async def setup(client, mint_token):
    campaign, dm, player = await _campaign_with_player(client, mint_token, suffix="guided")
    game = (
        await client.post(f"/campaigns/{campaign}/sessions", json={}, headers=_auth(dm))
    ).json()["id"]
    return f"/sessions/{game}", dm, player


def command(action, revision, **extra):
    return dict(action=action, revision=revision, request_id=str(uuid.uuid4()), **extra)


async def launch(client, path, dm, player):
    for token, action, revision in [(dm, "watch", 2), (player, "ready", 3), (dm, "begin", 4)]:
        response = await client.post(
            path + "/guided", headers=_auth(token), json=command(action, revision)
        )
        assert response.status_code == 200, response.text


@pytest.mark.parametrize("die,success", [(1, False), (20, True)])
async def test_complete_rescue_and_retry(auth_client, mint_token, monkeypatch, die, success):
    class Fixed:
        def randint(self, a, b):
            assert a <= die <= b
            return die

    monkeypatch.setattr(
        guided, "ability_check", lambda bonus, dc: ability_check(bonus, dc=dc, rng=Fixed())
    )
    path, dm, player = await setup(auth_client, mint_token)

    async def act(token, action, revision, **extra):
        r = await auth_client.post(
            path + "/guided", headers=_auth(token), json=command(action, revision, **extra)
        )
        assert r.status_code == 200, r.text
        return r.json()["state"]

    await act(dm, "start", 0)
    selected = await act(player, "select", 1, pregen="guardian")
    assert len(selected["participants"]) == 1
    await launch(auth_client, path, dm, player)
    pending = await act(player, "approach", 5, approach="lift")
    assert pending["pending"]["bonus"] == 5
    roll = command("roll", 6)
    response = await auth_client.post(path + "/guided", headers=_auth(player), json=roll)
    assert response.status_code == 200, response.text
    state = response.json()["state"]
    assert state["result"]["success"] == success
    assert state["result"]["total"] == die + 5
    assert state["pending"] is None
    repeated = await auth_client.post(path + "/guided", headers=_auth(player), json=roll)
    assert repeated.json() == response.json()
    assert len((await auth_client.get(path + "/log", headers=_auth(player))).json()) == 7
    conversation = await act(dm, "continue", 7)
    assert conversation["phase"] == "conversation"
    assert ("gate is closed" in conversation["conversation"]["intro"]) == (not success)
    await act(player, "ask", 8, topic="road")
    decision = await act(player, "choose", 9, choice="town")
    assert ("at dawn" in decision["conversation"]["ending"]["body"]) == (not success)
    await act(dm, "skip_practice", 10)
    # A new read recovers both final state and the outcome after completion.
    replay = (await auth_client.get(path + "/guided", headers=_auth(player))).json()["state"]
    assert replay["phase"] == "complete"
    assert replay["result"] == state["result"]
    repeated = await auth_client.post(path + "/guided", headers=_auth(player), json=roll)
    assert repeated.json()["state"] == replay


async def test_authority_stale_commands_and_ended_session(auth_client, mint_token):
    path, dm, player = await setup(auth_client, mint_token)

    async def post(token, cmd, status):
        response = await auth_client.post(path + "/guided", headers=_auth(token), json=cmd)
        assert response.status_code == status, response.text
        return response.json()

    await post(player, command("start", 0), 403)
    await post(dm, command("start", 0), 200)
    await post(player, command("select", 0, pregen="guardian"), 409)
    selected = await post(player, command("select", 1, pregen="scholar"), 200)
    character = next(iter(selected["state"]["participants"].values()))["character_id"]
    await post(dm, command("select", 2, character_id=character), 403)
    await launch(auth_client, path, dm, player)
    await post(player, command("select", 5, pregen="guardian"), 409)
    await post(player, command("approach", 5, approach="leverage"), 200)
    await post(dm, command("roll", 6), 403)
    await post(player, command("roll", 6, total=20), 422)
    await post(player, command("cancel", 6), 403)
    await post(dm, command("cancel", 6), 200)
    await post(player, command("roll", 6), 409)
    await post(player, command("approach", 7, approach="leverage"), 200)
    ended = await auth_client.post(path + "/end", headers=_auth(dm))
    assert ended.status_code == 200
    await post(player, command("roll", 8), 409)
    await post(dm, command("cancel", 8), 409)
    log = (await auth_client.get(path + "/log", headers=_auth(player))).json()
    assert log[-1]["payload"]["type"] == "session_ended"
    outsider = mint_token(sub="outsider", email="outsider@example.com")
    assert (await auth_client.get(path + "/guided", headers=_auth(outsider))).status_code == 403


async def test_reused_id_cannot_change_command(auth_client, mint_token):
    path, dm, _ = await setup(auth_client, mint_token)
    cmd = command("start", 0)
    assert (
        await auth_client.post(path + "/guided", headers=_auth(dm), json=cmd)
    ).status_code == 200
    cmd["action"] = "continue"
    assert (
        await auth_client.post(path + "/guided", headers=_auth(dm), json=cmd)
    ).status_code == 409


async def test_simultaneous_commands_have_one_winner(auth_client, mint_token, session):
    import asyncio

    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from boor_service.db.models import GameSession, User

    path, dm, player = await setup(auth_client, mint_token)
    await auth_client.post(path + "/guided", headers=_auth(dm), json=command("start", 0))
    ids = [(await auth_client.get("/me", headers=_auth(t))).json()["id"] for t in (dm, player)]
    await session.commit()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    game_id = uuid.UUID(path.split("/")[-1])

    async def choose(user_id):
        async with factory() as db:
            game = await db.get(GameSession, game_id)
            user = await db.get(User, uuid.UUID(user_id))
            assert game is not None and user is not None
            try:
                result = await guided.command_guided(
                    guided.Command(**command("select", 1, pregen="guardian")), game, user, db
                )
                return result["state"]["revision"]
            except HTTPException as e:
                await db.rollback()
                return e.status_code

    assert sorted(await asyncio.gather(*(choose(uid) for uid in ids))) == [2, 409]
    async with factory() as db:
        state = await guided.latest_state(db, game_id)
        assert state is not None and len(state["participants"]) == 1


@pytest.mark.parametrize(
    "action,extra",
    [
        ("pause", {}),
        ("pause_note", {"text": "x"}),
        ("resume", {}),
        ("propose", {"text": "x"}),
        ("accept_proposal", {"approach": "lift"}),
        ("decline_proposal", {"text": "x"}),
    ],
)
async def test_v5_only_actions_are_rejected_on_legacy_runs(auth_client, mint_token, action, extra):
    path, dm, player = await setup(auth_client, mint_token)
    await auth_client.post(path + "/guided", headers=_auth(dm), json=command("start", 0))
    await auth_client.post(
        path + "/guided", headers=_auth(player), json=command("select", 1, pregen="guardian")
    )
    await launch(auth_client, path, dm, player)
    # Reach the outcome step, where a fall-through would wrongly "continue".
    for token, step, extra2 in [(player, "approach", {"approach": "lift"}), (player, "roll", {})]:
        rev = (await auth_client.get(path + "/guided", headers=_auth(dm))).json()["state"]
        r = await auth_client.post(
            path + "/guided", headers=_auth(token), json=command(step, rev["revision"], **extra2)
        )
        assert r.status_code == 200, r.text
    before = (await auth_client.get(path + "/guided", headers=_auth(dm))).json()["state"]
    assert before["phase"] == "outcome"
    r = await auth_client.post(
        path + "/guided", headers=_auth(dm), json=command(action, before["revision"], **extra)
    )
    assert r.status_code == 409, r.text
    after = (await auth_client.get(path + "/guided", headers=_auth(dm))).json()["state"]
    assert after["revision"] == before["revision"] and after["phase"] == "outcome"
