"""AI-09: per-character recaps written when the DM ends a session.

Decided by Evan 2026-10-10: written automatically at session end for every
character the AI stand-in played; delivered in-app (email later); private to the
character's player and the DM until the player shares it with the table;
read-only, with "not my character" flags kept for profile learning (AI-10).
"""

import uuid

import pytest

from boor_service.ai.recap import RecapError
from boor_service.ai.table import get_standin_client
from boor_service.api import app
from boor_service.db.models import EventAudience, EventKind, GameSession
from boor_service.db.repository import append_event
from tests.test_session_api import _auth
from tests.test_standin import _client_calling
from tests.test_standin_table import configure, setup_table


async def _played_session(client, mint_token, session):
    """A session where the stand-in took one turn for the player's character, plus a
    DM-only secret and a second, never-AI character; returns ids and tokens."""
    campaign, game, character, dm, player = await setup_table(client, mint_token)
    await configure(client, character, player)
    path = f"/sessions/{game}/standins/{character}"
    assert (
        await client.put(path, json={"enabled": True}, headers=_auth(player))
    ).status_code == 200
    game_row = await session.get(GameSession, uuid.UUID(game))
    await append_event(
        session,
        game_session=game_row,
        kind=EventKind.narration,
        body="Secret DM-only password",
        audience=EventAudience.dm,
    )
    await session.commit()
    app.dependency_overrides[get_standin_client] = lambda: _client_calling(
        "speak", {"message": "Stay close.", "description": "Warn the party"}
    )
    turn = await client.post(
        path + "/turn", json={"request_id": str(uuid.uuid4())}, headers=_auth(dm)
    )
    assert turn.status_code == 200, turn.text
    # A second player whose character the AI never played gets no recap.
    other = mint_token(sub="clerk_other", email="other@example.com", name="Other")
    invite = (
        await client.post(
            f"/campaigns/{campaign}/invites", headers=_auth(dm), json={"email": "other@example.com"}
        )
    ).json()
    await client.post(f"/invites/{invite['token']}/accept", headers=_auth(other))
    await client.post(
        f"/campaigns/{campaign}/characters",
        headers=_auth(other),
        json={
            "name": "Rowan",
            "abilities": dict.fromkeys(["str", "dex", "con", "int", "wis", "cha"], 12),
            "max_hp": 10,
        },
    )
    return campaign, game, character, dm, player, other


async def _end(client, game, dm):
    response = await client.post(f"/sessions/{game}/end", headers=_auth(dm))
    assert response.status_code == 200, response.text


async def _recaps(client, campaign, token):
    response = await client.get(f"/campaigns/{campaign}/recaps", headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


async def test_ending_a_session_writes_a_recap_for_each_stand_in_character(
    auth_client, mint_token, session, fake_recap_writer
):
    campaign, game, character, dm, player, _other = await _played_session(
        auth_client, mint_token, session
    )
    await _end(auth_client, game, dm)
    recaps = await _recaps(auth_client, campaign, player)
    assert len(recaps) == 1
    recap = recaps[0]
    assert recap["character_id"] == character and recap["character_name"] == "Pip"
    assert recap["session_id"] == game
    assert recap["status"] == "ready" and recap["body"].startswith("I kept watch.")
    assert recap["mine"] is True and recap["read"] is False and recap["shared"] is False
    # Built only from what Pip could know, with Pip's own stand-in decisions called out.
    ctx = fake_recap_writer.calls[0]
    assert "Secret DM-only password" not in ctx.timeline
    assert ctx.own_actions == ["Stay close."]
    assert "cautious scout" in ctx.persona
    # Ending again writes nothing new.
    await auth_client.post(f"/sessions/{game}/end", headers=_auth(dm))
    assert len(fake_recap_writer.calls) == 1


@pytest.mark.usefixtures("fake_recap_writer")
async def test_recaps_are_private_until_the_player_shares(auth_client, mint_token, session):
    campaign, game, _character, dm, player, other = await _played_session(
        auth_client, mint_token, session
    )
    await _end(auth_client, game, dm)
    assert len(await _recaps(auth_client, campaign, dm)) == 1
    assert await _recaps(auth_client, campaign, other) == []
    recap_id = (await _recaps(auth_client, campaign, player))[0]["id"]
    # Only the character's player may share it (not the DM, not another player).
    for token in (dm, other):
        assert (
            await auth_client.post(f"/recaps/{recap_id}/share", headers=_auth(token))
        ).status_code == 403
    assert (
        await auth_client.post(f"/recaps/{recap_id}/share", headers=_auth(player))
    ).status_code == 200
    shared = await _recaps(auth_client, campaign, other)
    assert len(shared) == 1 and shared[0]["shared"] is True and shared[0]["mine"] is False
    outsider = mint_token(sub="clerk_out", email="out@example.com")
    assert (
        await auth_client.get(f"/campaigns/{campaign}/recaps", headers=_auth(outsider))
    ).status_code == 403


@pytest.mark.usefixtures("fake_recap_writer")
async def test_read_marks_and_out_of_character_flags(auth_client, mint_token, session):
    campaign, game, _character, dm, player, other = await _played_session(
        auth_client, mint_token, session
    )
    await _end(auth_client, game, dm)
    recap_id = (await _recaps(auth_client, campaign, player))[0]["id"]
    assert (
        await auth_client.post(f"/recaps/{recap_id}/read", headers=_auth(dm))
    ).status_code == 403
    assert (
        await auth_client.post(f"/recaps/{recap_id}/read", headers=_auth(player))
    ).status_code == 200
    assert (await _recaps(auth_client, campaign, player))[0]["read"] is True

    flag = {"quote": "I'd do it again.", "note": "Pip would never brag."}
    assert (
        await auth_client.post(f"/recaps/{recap_id}/flags", json=flag, headers=_auth(dm))
    ).status_code == 403
    assert (
        await auth_client.post(
            f"/recaps/{recap_id}/flags", json={"quote": " ", "note": ""}, headers=_auth(player)
        )
    ).status_code == 422
    assert (
        await auth_client.post(f"/recaps/{recap_id}/flags", json=flag, headers=_auth(player))
    ).status_code == 200
    # Flags are for the player and the DM; the recap text itself never changes.
    for token in (player, dm):
        recap = (await _recaps(auth_client, campaign, token))[0]
        assert recap["flags"][0]["quote"] == "I'd do it again."
        assert recap["body"].endswith("I'd do it again.")
    await auth_client.post(f"/recaps/{recap_id}/share", headers=_auth(player))
    assert (await _recaps(auth_client, campaign, other))[0]["flags"] == []


async def test_a_failed_recap_is_kept_and_the_dm_can_retry(
    auth_client, mint_token, session, fake_recap_writer
):
    fake_recap_writer.result = RecapError("model refused")
    campaign, game, _character, dm, player, _other = await _played_session(
        auth_client, mint_token, session
    )
    await _end(auth_client, game, dm)
    recap = (await _recaps(auth_client, campaign, player))[0]
    assert recap["status"] == "failed" and recap["body"] == ""
    assert (
        await auth_client.post(f"/recaps/{recap['id']}/retry", headers=_auth(player))
    ).status_code == 403
    fake_recap_writer.result = "Second try. I stayed close."
    assert (
        await auth_client.post(f"/recaps/{recap['id']}/retry", headers=_auth(dm))
    ).status_code == 200
    recap = (await _recaps(auth_client, campaign, player))[0]
    assert recap["status"] == "ready" and recap["body"] == "Second try. I stayed close."
    # Retrying a ready recap is refused (no silent rewrites of what happened).
    assert (
        await auth_client.post(f"/recaps/{recap['id']}/retry", headers=_auth(dm))
    ).status_code == 409


async def test_recaps_fail_visibly_when_ai_is_off(auth_client, mint_token, session, monkeypatch):
    from boor_service import recaps as recaps_module

    monkeypatch.setattr(recaps_module, "get_client", lambda: None)
    campaign, game, _character, dm, _player, _other = await _played_session(
        auth_client, mint_token, session
    )
    await _end(auth_client, game, dm)
    recap = (await _recaps(auth_client, campaign, dm))[0]
    assert recap["status"] == "failed" and "not enabled" in recap["error"]
