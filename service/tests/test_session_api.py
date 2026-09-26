"""End-to-end tests for the play-session BFF surface (DATA-03, the MILE-1 table).

Drives the real HTTP app through the Clerk auth stack, same as ``test_bff.py``:
open a session (DM only), list/read it (any member), replay its timeline, and end
it (DM only) — plus the authorization boundaries a non-member/non-DM hits.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service.db.models import EventAudience, EventKind, GameSession
from boor_service.db.repository import append_event


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _campaign_with_player(
    client: httpx.AsyncClient,
    mint_token: Callable[..., str],
    *,
    suffix: str,
) -> tuple[str, str, str]:
    """Create a campaign with a DM and a joined player; return (campaign_id, dm, player)."""
    dm = mint_token(sub=f"clerk_dm_{suffix}", email=f"dm_{suffix}@example.com")
    player = mint_token(sub=f"clerk_pl_{suffix}", email=f"pl_{suffix}@example.com")
    campaign_id = (
        await client.post("/campaigns", json={"name": f"Camp {suffix}"}, headers=_auth(dm))
    ).json()["id"]
    token = (
        await client.post(
            f"/campaigns/{campaign_id}/invites",
            json={"email": f"pl_{suffix}@example.com"},
            headers=_auth(dm),
        )
    ).json()["token"]
    await client.post(f"/invites/{token}/accept", headers=_auth(player))
    return campaign_id, dm, player


async def test_dm_opens_session_active_and_members_can_read(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    campaign_id, dm, player = await _campaign_with_player(auth_client, mint_token, suffix="a")

    created = await auth_client.post(
        f"/campaigns/{campaign_id}/sessions",
        json={"title": "Session Zero"},
        headers=_auth(dm),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "active"
    assert body["title"] == "Session Zero"
    assert body["started_at"] is not None
    session_id = body["id"]

    # any member (the player) may list and read the session
    listed = await auth_client.get(f"/campaigns/{campaign_id}/sessions", headers=_auth(player))
    assert [s["id"] for s in listed.json()] == [session_id]

    got = await auth_client.get(f"/sessions/{session_id}", headers=_auth(player))
    assert got.status_code == 200
    assert got.json()["id"] == session_id


async def test_only_dm_can_open_a_session(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    campaign_id, _dm, player = await _campaign_with_player(auth_client, mint_token, suffix="b")
    resp = await auth_client.post(
        f"/campaigns/{campaign_id}/sessions", json={}, headers=_auth(player)
    )
    assert resp.status_code == 403


async def test_non_member_cannot_read_session(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    campaign_id, dm, _player = await _campaign_with_player(auth_client, mint_token, suffix="c")
    session_id = (
        await auth_client.post(f"/campaigns/{campaign_id}/sessions", json={}, headers=_auth(dm))
    ).json()["id"]

    outsider = mint_token(sub="clerk_out_c", email="out_c@example.com")
    resp = await auth_client.get(f"/sessions/{session_id}", headers=_auth(outsider))
    assert resp.status_code == 403


async def test_unknown_session_is_404(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    caller = mint_token(sub="clerk_404", email="s404@example.com")
    resp = await auth_client.get(f"/sessions/{uuid.uuid4()}", headers=_auth(caller))
    assert resp.status_code == 404


async def test_session_log_replays_the_timeline(
    auth_client: httpx.AsyncClient,
    mint_token: Callable[..., str],
    session_log_seeder: Callable[..., Awaitable[None]],
) -> None:
    campaign_id, dm, player = await _campaign_with_player(auth_client, mint_token, suffix="d")
    session_id = (
        await auth_client.post(f"/campaigns/{campaign_id}/sessions", json={}, headers=_auth(dm))
    ).json()["id"]

    # seed a couple of timeline entries directly (as the realtime handler would)
    await session_log_seeder(session_id)

    log = await auth_client.get(f"/sessions/{session_id}/log", headers=_auth(player))
    assert log.status_code == 200
    entries = log.json()
    assert [e["kind"] for e in entries] == ["narration", "roll"]
    assert entries[0]["body"] == "The door creaks open."
    assert entries[1]["payload"] == {"total": 12}
    assert [e["seq"] for e in entries] == [1, 2]
    assert [e["audience"] for e in entries] == ["table", "table"]


_THORA = {
    "name": "Thora",
    "level": 5,
    "abilities": {"str": 18, "dex": 12, "con": 16, "int": 8, "wis": 13, "cha": 10},
    "max_hp": 44,
    "base_armor_class": 18,
}

_LYRA = {
    "name": "Lyra",
    "level": 5,
    "abilities": {"str": 10, "dex": 12, "con": 14, "int": 11, "wis": 18, "cha": 13},
    "max_hp": 33,
    "base_armor_class": 16,
}


async def test_session_log_is_scoped_to_the_viewer(
    auth_client: httpx.AsyncClient,
    mint_token: Callable[..., str],
    session: AsyncSession,
) -> None:
    """A player replaying the log cannot see another PC's whisper or DM notes."""
    campaign_id, dm, player = await _campaign_with_player(auth_client, mint_token, suffix="scope")
    other = mint_token(sub="clerk_pl_scope2", email="pl_scope2@example.com")
    token = (
        await auth_client.post(
            f"/campaigns/{campaign_id}/invites",
            json={"email": "pl_scope2@example.com"},
            headers=_auth(dm),
        )
    ).json()["token"]
    await auth_client.post(f"/invites/{token}/accept", headers=_auth(other))

    session_id = (
        await auth_client.post(f"/campaigns/{campaign_id}/sessions", json={}, headers=_auth(dm))
    ).json()["id"]
    thora_id = (
        await auth_client.post(
            f"/campaigns/{campaign_id}/characters", json=_THORA, headers=_auth(player)
        )
    ).json()["id"]
    await auth_client.post(f"/campaigns/{campaign_id}/characters", json=_LYRA, headers=_auth(other))

    game_session = await session.get(GameSession, uuid.UUID(session_id))
    assert game_session is not None
    await append_event(session, game_session=game_session, kind=EventKind.narration, body="Public.")
    await append_event(
        session,
        game_session=game_session,
        kind=EventKind.in_character,
        body="Thora's secret.",
        audience=EventAudience.characters,
        visible_to=[thora_id],
    )
    await append_event(
        session,
        game_session=game_session,
        kind=EventKind.system,
        body="DM only.",
        audience=EventAudience.dm,
    )
    await session.commit()

    player_log = (
        await auth_client.get(f"/sessions/{session_id}/log", headers=_auth(player))
    ).json()
    other_log = (await auth_client.get(f"/sessions/{session_id}/log", headers=_auth(other))).json()
    dm_log = (await auth_client.get(f"/sessions/{session_id}/log", headers=_auth(dm))).json()

    assert [e["body"] for e in player_log] == ["Public.", "Thora's secret."]
    assert [e["body"] for e in other_log] == ["Public."]
    assert [e["body"] for e in dm_log] == ["Public.", "Thora's secret.", "DM only."]


async def test_dm_ends_session_player_cannot(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    campaign_id, dm, player = await _campaign_with_player(auth_client, mint_token, suffix="e")
    session_id = (
        await auth_client.post(f"/campaigns/{campaign_id}/sessions", json={}, headers=_auth(dm))
    ).json()["id"]

    # a player may not end the session
    refused = await auth_client.post(f"/sessions/{session_id}/end", headers=_auth(player))
    assert refused.status_code == 403

    ended = await auth_client.post(f"/sessions/{session_id}/end", headers=_auth(dm))
    assert ended.status_code == 200
    assert ended.json()["status"] == "ended"
    assert ended.json()["ended_at"] is not None
