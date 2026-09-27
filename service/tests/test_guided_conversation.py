"""Shared conversation choices, state recovery and permission boundaries."""

import asyncio
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker

from boor_service import guided
from boor_service.db.models import GameSession, User
from tests.test_guided import command, setup
from tests.test_session_api import _auth


async def open_conversation(client, mint_token, *, host_plays=False):
    path, host, player = await setup(client, mint_token)
    steps = [(host, "start", {}), (player, "select", {"pregen": "scholar"}), (player, "ready", {})]
    if host_plays:
        steps += [(host, "select", {"pregen": "guardian"}), (host, "ready", {})]
    else:
        steps += [(host, "watch", {})]
    steps += [
        (host, "begin", {}),
        (player, "approach", {"approach": "leverage"}),
        (player, "roll", {}),
        (host, "continue", {}),
    ]
    state = None
    for revision, (token, action, extra) in enumerate(steps):
        response = await client.post(
            path + "/guided", headers=_auth(token), json=command(action, revision, **extra)
        )
        assert response.status_code == 200, response.text
        state = response.json()["state"]
    assert state is not None and state["phase"] == "conversation"
    return path, host, player, state


async def test_dialogue_no_rolls_shared_answers_and_one_destination(
    auth_client, mint_token, monkeypatch
):
    path, host, player, state = await open_conversation(auth_client, mint_token)
    revision = state["revision"]

    def no_roll(*_args, **_kwargs):
        raise AssertionError("Friendly conversation must not roll dice")

    monkeypatch.setattr(guided, "ability_check", no_roll)

    async def post(token, action, rev, **extra):
        return await auth_client.post(
            path + "/guided", headers=_auth(token), json=command(action, rev, **extra)
        )

    assert (await post(host, "ask", revision, topic="road")).status_code == 403
    assert (await post(player, "choose", revision, choice="river")).status_code == 409
    assert (await post(host, "continue", revision)).status_code == 409
    assert (await post(player, "ask", revision, topic="unknown")).status_code == 422
    ask = command("ask", revision, topic="river")
    first = await auth_client.post(path + "/guided", headers=_auth(player), json=ask)
    assert first.status_code == 200
    retry = await auth_client.post(path + "/guided", headers=_auth(player), json=ask)
    assert retry.json() == first.json()
    revision += 1
    assert (await post(player, "ask", revision, topic="river")).status_code == 409
    assert (await post(host, "choose", revision, choice="town")).status_code == 403
    assert (await post(player, "ask", revision, topic="mara")).status_code == 200
    revision += 1
    replay = (await auth_client.get(path + "/guided", headers=_auth(host))).json()["state"]
    assert len(replay["conversation"]["answers"]) == 2
    assert "blankets" in replay["conversation"]["answers"][1]["reply"]
    choose = command("choose", revision, choice="river")
    selected = await auth_client.post(path + "/guided", headers=_auth(player), json=choose)
    assert selected.status_code == 200
    assert selected.json()["state"]["phase"] == "decision"
    revision += 1
    assert (await post(player, "choose", revision, choice="town")).status_code == 409
    assert (await post(player, "continue", revision)).status_code == 403
    assert (await post(host, "skip_practice", revision)).status_code == 200
    retry = await auth_client.post(path + "/guided", headers=_auth(player), json=choose)
    assert retry.json()["state"]["phase"] == "complete"
    assert retry.json()["state"]["conversation"]["ending"]["choice"] == "river"
    assert (await auth_client.post(path + "/end", headers=_auth(host))).status_code == 200
    assert (await post(player, "ask", revision + 1, topic="road")).status_code == 409


async def test_two_players_cannot_commit_conflicting_destinations(auth_client, mint_token, session):
    path, host, player, state = await open_conversation(auth_client, mint_token, host_plays=True)
    response = await auth_client.post(
        path + "/guided",
        headers=_auth(player),
        json=command("ask", state["revision"], topic="road"),
    )
    assert response.status_code == 200
    revision = response.json()["state"]["revision"]
    ids = [(await auth_client.get("/me", headers=_auth(t))).json()["id"] for t in (host, player)]
    await session.commit()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    game_id = uuid.UUID(path.split("/")[-1])

    async def choose(user_id, choice):
        async with factory() as db:
            game = await db.get(GameSession, game_id)
            user = await db.get(User, uuid.UUID(user_id))
            assert game is not None and user is not None
            try:
                await guided.command_guided(
                    guided.Command(**command("choose", revision, choice=choice)), game, user, db
                )
                return 200
            except HTTPException as e:
                await db.rollback()
                return e.status_code

    assert sorted(await asyncio.gather(choose(ids[0], "town"), choose(ids[1], "river"))) == [
        200,
        409,
    ]
    async with factory() as db:
        recovered = await guided.latest_state(db, game_id)
        assert recovered is not None
        assert recovered["revision"] == revision + 1
        assert recovered["phase"] == "decision"
        assert recovered["conversation"]["ending"]["choice"] in {"town", "river"}
