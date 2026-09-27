"""Table integration: real auth/DB/rules/guardrails with a scripted model."""

import asyncio
import uuid

import pytest
from fastapi import HTTPException

from boor_service.ai import table
from boor_service.ai.table import get_standin_client
from boor_service.api import app
from boor_service.db.models import EventAudience, EventKind, GameSession
from boor_service.db.repository import append_event
from tests.test_session_api import _auth, _campaign_with_player
from tests.test_standin import _client_calling


async def setup_table(client, mint_token):
    campaign, dm, player = await _campaign_with_player(client, mint_token, suffix="ai")
    game = (
        await client.post(f"/campaigns/{campaign}/sessions", json={}, headers=_auth(dm))
    ).json()["id"]
    character = (
        await client.post(
            f"/campaigns/{campaign}/characters",
            headers=_auth(player),
            json={
                "name": "Pip",
                "abilities": dict.fromkeys(["str", "dex", "con", "int", "wis", "cha"], 12),
                "max_hp": 10,
            },
        )
    ).json()["id"]
    return campaign, game, character, dm, player


async def configure(client, character, player):
    response = await client.put(
        f"/characters/{character}/standin-profile",
        headers=_auth(player),
        json={
            "persona": "A cautious scout who speaks in short sentences.",
            "standing_instructions": "Protect the party.",
            "red_lines": [{"kind": "no_attacking_allies"}],
        },
    )
    assert response.status_code == 200


async def test_control_permissions_and_atomic_profile_replacement(auth_client, mint_token):
    _, game, character, dm, player = await setup_table(auth_client, mint_token)
    path = f"/sessions/{game}/standins/{character}"
    assert (
        await auth_client.put(path, json={"enabled": True}, headers=_auth(player))
    ).status_code == 409
    await configure(auth_client, character, player)
    await configure(auth_client, character, player)
    lines = (
        await auth_client.get(f"/characters/{character}/red-lines", headers=_auth(player))
    ).json()
    assert len(lines) == 1
    assert (
        await auth_client.put(path, json={"enabled": True}, headers=_auth(player))
    ).status_code == 200
    outsider = mint_token(sub="outsider", email="outsider@example.com")
    assert (
        await auth_client.put(path, json={"enabled": False}, headers=_auth(outsider))
    ).status_code == 403
    assert (
        await auth_client.put(path, json={"enabled": False}, headers=_auth(player))
    ).status_code == 200
    await auth_client.post(f"/sessions/{game}/end", headers=_auth(dm))
    assert (
        await auth_client.put(path, json={"enabled": True}, headers=_auth(dm))
    ).status_code == 409


async def test_turn_is_dm_only_scoped_attributed_and_idempotent(auth_client, mint_token, session):
    _, game, character, dm, player = await setup_table(auth_client, mint_token)
    await configure(auth_client, character, player)
    path = f"/sessions/{game}/standins/{character}"
    await auth_client.put(path, json={"enabled": True}, headers=_auth(player))
    game_row = await session.get(GameSession, uuid.UUID(game))
    await append_event(
        session,
        game_session=game_row,
        kind=EventKind.narration,
        body="Secret DM-only password",
        audience=EventAudience.dm,
    )
    await session.commit()
    fake = _client_calling("speak", {"message": "Stay close.", "description": "Warn the party"})
    app.dependency_overrides[get_standin_client] = lambda: fake
    body = {"request_id": str(uuid.uuid4())}
    assert (
        await auth_client.post(path + "/turn", json=body, headers=_auth(player))
    ).status_code == 403
    response = await auth_client.post(path + "/turn", json=body, headers=_auth(dm))
    assert response.status_code == 200, response.text
    event = response.json()
    assert event["ai_generated"] is True
    assert "Secret DM-only password" not in str(fake.messages.calls)
    repeat = await auth_client.post(path + "/turn", json=body, headers=_auth(dm))
    assert repeat.json()["seq"] == event["seq"]
    assert len(fake.messages.calls) == 1
    await auth_client.put(path, json={"enabled": False}, headers=_auth(player))
    assert (
        await auth_client.post(
            path + "/turn", json={"request_id": str(uuid.uuid4())}, headers=_auth(dm)
        )
    ).status_code == 409


async def test_boundary_refusal_is_logged_without_rolling(auth_client, mint_token):
    _, game, character, dm, player = await setup_table(auth_client, mint_token)
    await configure(auth_client, character, player)
    await auth_client.put(
        f"/characters/{character}/standin-profile",
        headers=_auth(player),
        json={
            "persona": "Peaceful scout",
            "red_lines": [{"kind": "forbid_action_types", "action_types": ["speak"]}],
        },
    )
    path = f"/sessions/{game}/standins/{character}"
    await auth_client.put(path, json={"enabled": True}, headers=_auth(player))
    app.dependency_overrides[get_standin_client] = lambda: _client_calling(
        "speak", {"message": "Hello"}
    )
    response = await auth_client.post(
        path + "/turn", json={"request_id": str(uuid.uuid4())}, headers=_auth(dm)
    )
    assert response.status_code == 200, response.text
    assert response.json()["payload"]["allowed"] is False
    assert response.json()["payload"]["refusal"]


async def test_timeout_clears_busy_state(auth_client, mint_token, monkeypatch):
    _, game, character, dm, player = await setup_table(auth_client, mint_token)
    await configure(auth_client, character, player)
    path = f"/sessions/{game}/standins/{character}"
    await auth_client.put(path, json={"enabled": True}, headers=_auth(player))
    app.dependency_overrides[get_standin_client] = lambda: _client_calling(
        "speak", {"message": "Hello"}
    )

    async def timeout(coro, **_kwargs):
        coro.close()
        raise TimeoutError

    monkeypatch.setattr(asyncio, "wait_for", timeout)
    response = await auth_client.post(
        path + "/turn", json={"request_id": str(uuid.uuid4())}, headers=_auth(dm)
    )
    assert response.status_code == 504
    assert uuid.UUID(game) not in table._busy


def test_live_model_is_opt_in(monkeypatch):
    monkeypatch.delenv("ENABLE_STANDINS", raising=False)
    with pytest.raises(HTTPException) as exc:
        next(get_standin_client())
    assert exc.value.status_code == 503


async def test_taking_back_control_discards_inflight_result(auth_client, mint_token, monkeypatch):
    _, game, character, dm, player = await setup_table(auth_client, mint_token)
    await configure(auth_client, character, player)
    path = f"/sessions/{game}/standins/{character}"
    await auth_client.put(path, json={"enabled": True}, headers=_auth(player))
    app.dependency_overrides[get_standin_client] = lambda: _client_calling(
        "speak", {"message": "Hello"}
    )

    async def take_back_then_decide(function, *args, **kwargs):
        response = await auth_client.put(path, json={"enabled": False}, headers=_auth(player))
        assert response.status_code == 200
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", take_back_then_decide)
    response = await auth_client.post(
        path + "/turn", json={"request_id": str(uuid.uuid4())}, headers=_auth(dm)
    )
    assert response.status_code == 409
    log = (await auth_client.get(f"/sessions/{game}/log", headers=_auth(dm))).json()
    assert not any(event["ai_generated"] for event in log)


async def test_overlapping_turn_is_rejected(auth_client, mint_token):
    _, game, character, dm, player = await setup_table(auth_client, mint_token)
    await configure(auth_client, character, player)
    path = f"/sessions/{game}/standins/{character}"
    await auth_client.put(path, json={"enabled": True}, headers=_auth(player))
    app.dependency_overrides[get_standin_client] = lambda: _client_calling(
        "speak", {"message": "Hello"}
    )
    table._busy.add(uuid.UUID(game))
    try:
        response = await auth_client.post(
            path + "/turn", json={"request_id": str(uuid.uuid4())}, headers=_auth(dm)
        )
        assert response.status_code == 409
    finally:
        table._busy.discard(uuid.UUID(game))
