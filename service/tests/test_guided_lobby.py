"""The lobby gates play on explicit readiness and preserves version-one runs."""

import uuid

import pytest

from boor_service.db.models import EventKind, GameSession
from boor_service.db.repository import append_event
from tests.test_guided import command, setup
from tests.test_session_api import _auth


async def test_lobby_ready_watch_reselect_and_begin(auth_client, mint_token):
    path, host, player = await setup(auth_client, mint_token)
    revision = 0

    async def act(token, action, expected=200, **extra):
        nonlocal revision
        response = await auth_client.post(
            path + "/guided", headers=_auth(token), json=command(action, revision, **extra)
        )
        assert response.status_code == expected, response.text
        if expected == 200:
            state = response.json()["state"]
            revision = state["revision"]
            return state

    state = await act(host, "start")
    assert state["phase"] == "lobby" and state["version"] == 4
    assert len(state["seats"]) == 2
    await act(host, "begin", 409)
    await act(player, "ready", 409)
    await act(player, "select", pregen="guardian")
    await act(player, "approach", 409, approach="lift")
    await act(player, "ready")
    await act(host, "begin", 409)
    await act(host, "watch")
    await act(player, "begin", 403)
    state = await act(player, "select", pregen="scholar")
    assert not all(s["ready"] for s in state["seats"].values())
    await act(host, "begin", 409)
    await act(player, "select", pregen="guardian")
    await act(player, "ready")
    state = await act(host, "begin")
    assert state["phase"] == "ready"
    # Repeated selection reuses starter sheets instead of creating duplicates.
    campaign = (await auth_client.get(path, headers=_auth(host))).json()["campaign_id"]
    chars = (await auth_client.get(f"/campaigns/{campaign}/characters", headers=_auth(host))).json()
    assert len(chars) == 2
    await act(player, "unready", 409)
    await act(player, "join", 409)
    await act(host, "approach", 409, approach="lift")
    await act(player, "approach", approach="lift")


async def test_absent_rejoin_and_readiness_replay(auth_client, mint_token):
    path, host, player = await setup(auth_client, mint_token)
    player_id = (await auth_client.get("/me", headers=_auth(player))).json()["id"]

    async def post(token, action, revision, **extra):
        return await auth_client.post(
            path + "/guided", headers=_auth(token), json=command(action, revision, **extra)
        )

    assert (await post(host, "start", 0)).status_code == 200
    assert (await post(player, "exclude", 1, target_user_id=player_id)).status_code == 403
    assert (await post(host, "exclude", 1, target_user_id=player_id)).status_code == 200
    assert (await post(player, "select", 2, pregen="guardian")).status_code == 409
    assert (await post(player, "join", 2)).status_code == 200
    assert (await post(player, "watch", 3)).status_code == 200
    assert (await post(host, "watch", 4)).status_code == 200
    # An all-spectator lobby cannot start.
    assert (await post(host, "begin", 5)).status_code == 409
    replay = (await auth_client.get(path + "/guided", headers=_auth(host))).json()["state"]
    assert replay["seats"][player_id]["ready"]
    assert replay["seats"][player_id]["watching"]
    assert (await post(host, "select", 5, pregen="guardian")).status_code == 200
    assert (await post(host, "ready", 6)).status_code == 200
    assert (await post(host, "begin", 7)).status_code == 200


@pytest.mark.parametrize("version", [1, 2])
async def test_legacy_ready_state_and_receipts_still_work(
    auth_client, mint_token, session, version
):
    path, host, _ = await setup(auth_client, mint_token)
    user = (await auth_client.get("/me", headers=_auth(host))).json()
    from boor_service.db.models import User

    actor = await session.get(User, uuid.UUID(user["id"]))
    game = await session.get(GameSession, uuid.UUID(path.split("/")[-1]))
    assert game is not None
    old_command = command("start", 0)
    await append_event(
        session,
        game_session=game,
        kind=EventKind.narration,
        actor=actor,
        payload={
            "type": f"guided_cart_v{version}",
            "request_id": old_command["request_id"],
            "command": old_command,
            "state": {
                "version": version,
                "revision": 1,
                "phase": "ready" if version == 1 else "lobby",
                "seats": {user["id"]: {"player_name": "Host", "ready": False, "watching": False}},
                "starters": {},
                "participants": {},
                "pending": None,
                "result": None,
                "intro": "Original introduction",
            },
        },
    )
    await session.commit()
    retry = await auth_client.post(path + "/guided", headers=_auth(host), json=old_command)
    assert retry.status_code == 200
    assert retry.json()["state"]["version"] == version
    steps = [("select", {"pregen": "guardian"})]
    if version == 2:
        steps += [("ready", {}), ("begin", {})]
    steps += [("approach", {"approach": "lift"}), ("roll", {}), ("continue", {})]
    for rev, (action, extra) in enumerate(steps, start=1):
        response = await auth_client.post(
            path + "/guided", headers=_auth(host), json=command(action, rev, **extra)
        )
        assert response.status_code == 200, response.text
    assert response.json()["state"]["phase"] == "complete"
    assert not response.json()["state"].get("conversation")


async def test_selected_player_can_switch_to_watching_and_resume(auth_client, mint_token):
    """Reported flow: host watches, player selects, then chooses to watch too."""
    path, host, player = await setup(auth_client, mint_token)
    host_id = (await auth_client.get("/me", headers=_auth(host))).json()["id"]
    player_id = (await auth_client.get("/me", headers=_auth(player))).json()["id"]
    for token, action, revision, extra in [
        (host, "start", 0, {}),
        (host, "watch", 1, {}),
        (player, "select", 2, {"pregen": "scholar"}),
    ]:
        response = await auth_client.post(
            path + "/guided", headers=_auth(token), json=command(action, revision, **extra)
        )
        assert response.status_code == 200, response.text
    watch = command("watch", 3)
    for _ in range(2):  # An ambiguous network retry must keep the same outcome.
        response = await auth_client.post(path + "/guided", headers=_auth(player), json=watch)
        assert response.status_code == 200, response.text
        state = response.json()["state"]
        assert state["revision"] == 4
        assert state["participants"] == {}
        assert state["seats"][player_id]["watching"]
        assert state["seats"][player_id]["ready"]
        assert state["seats"][host_id]["watching"]
    for token in [host, player]:
        replay = (await auth_client.get(path + "/guided", headers=_auth(token))).json()["state"]
        assert replay == state
    blocked = await auth_client.post(
        path + "/guided", headers=_auth(host), json=command("begin", 4)
    )
    assert blocked.status_code == 409  # Everyone watching cannot start play.
    for token, action, revision, extra in [
        (player, "select", 4, {"pregen": "scholar"}),
        (player, "ready", 5, {}),
        (host, "begin", 6, {}),
    ]:
        response = await auth_client.post(
            path + "/guided", headers=_auth(token), json=command(action, revision, **extra)
        )
        assert response.status_code == 200, response.text
    assert response.json()["state"]["phase"] == "ready"
