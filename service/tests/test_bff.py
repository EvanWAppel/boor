"""End-to-end tests for the authenticated BFF surface (AUTH-03, DATA-01/02/04).

Drives the real HTTP app through the Clerk auth stack: every request carries a
minted token (verified by the local-keypair verifier), hits the FastAPI routes,
and exercises the repository against the ephemeral Postgres. Covers the whole
loop a table goes through — create campaign, invite, accept, add a character, set
its stand-in persona and red lines — plus the authorization boundaries.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import httpx


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_THORA = {
    "name": "Thora",
    "level": 5,
    "abilities": {"str": 18, "dex": 12, "con": 16, "int": 8, "wis": 13, "cha": 10},
    "max_hp": 44,
    "skill_proficiencies": ["athletics", "perception"],
    "base_armor_class": 18,
}


async def test_me_requires_a_token(auth_client: httpx.AsyncClient) -> None:
    assert (await auth_client.get("/me")).status_code == 401


async def test_me_returns_mirrored_user(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    token = mint_token(sub="clerk_me", email="me@example.com", name="Me")
    resp = await auth_client.get("/me", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


async def test_create_and_list_campaigns(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    dm = mint_token(sub="clerk_dm", email="dm@example.com")

    created = await auth_client.post(
        "/campaigns", json={"name": "The Ninth Toll"}, headers=_auth(dm)
    )
    assert created.status_code == 201
    assert created.json()["my_role"] == "dm"

    listed = await auth_client.get("/campaigns", headers=_auth(dm))
    assert listed.status_code == 200
    assert [c["name"] for c in listed.json()] == ["The Ninth Toll"]


async def test_invite_accept_and_roster(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    dm = mint_token(sub="clerk_dm2", email="dm2@example.com")
    player = mint_token(sub="clerk_p1", email="player1@example.com")

    campaign_id = (
        await auth_client.post("/campaigns", json={"name": "Party"}, headers=_auth(dm))
    ).json()["id"]

    invite = await auth_client.post(
        f"/campaigns/{campaign_id}/invites",
        json={"email": "player1@example.com"},
        headers=_auth(dm),
    )
    assert invite.status_code == 201
    token = invite.json()["token"]

    accepted = await auth_client.post(f"/invites/{token}/accept", headers=_auth(player))
    assert accepted.status_code == 200
    assert accepted.json()["campaign_id"] == campaign_id
    assert accepted.json()["role"] == "player"

    roster = await auth_client.get(f"/campaigns/{campaign_id}/members", headers=_auth(player))
    assert roster.status_code == 200
    assert sorted(m["role"] for m in roster.json()) == ["dm", "player"]


async def test_non_member_cannot_read_roster(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    dm = mint_token(sub="clerk_dm3", email="dm3@example.com")
    outsider = mint_token(sub="clerk_out", email="out@example.com")
    campaign_id = (
        await auth_client.post("/campaigns", json={"name": "Closed"}, headers=_auth(dm))
    ).json()["id"]

    resp = await auth_client.get(f"/campaigns/{campaign_id}/members", headers=_auth(outsider))
    assert resp.status_code == 403


async def test_only_dm_can_invite(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    dm = mint_token(sub="clerk_dm4", email="dm4@example.com")
    player = mint_token(sub="clerk_p2", email="player2@example.com")
    campaign_id = (
        await auth_client.post("/campaigns", json={"name": "Gate"}, headers=_auth(dm))
    ).json()["id"]
    token = (
        await auth_client.post(
            f"/campaigns/{campaign_id}/invites",
            json={"email": "player2@example.com"},
            headers=_auth(dm),
        )
    ).json()["token"]
    await auth_client.post(f"/invites/{token}/accept", headers=_auth(player))

    # the player (a member, not the DM) may not invite others
    resp = await auth_client.post(
        f"/campaigns/{campaign_id}/invites",
        json={"email": "another@example.com"},
        headers=_auth(player),
    )
    assert resp.status_code == 403


async def test_create_character_validates_sheet(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    dm = mint_token(sub="clerk_dm5", email="dm5@example.com")
    campaign_id = (
        await auth_client.post("/campaigns", json={"name": "Sheet"}, headers=_auth(dm))
    ).json()["id"]

    bad = {"name": "Broken", "level": 1, "abilities": {"str": 10}, "max_hp": 8}
    resp = await auth_client.post(
        f"/campaigns/{campaign_id}/characters", json=bad, headers=_auth(dm)
    )
    assert resp.status_code == 400
    assert "ability" in resp.json()["detail"]


async def test_create_and_get_character(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    dm = mint_token(sub="clerk_dm6", email="dm6@example.com")
    campaign_id = (
        await auth_client.post("/campaigns", json={"name": "Heroes"}, headers=_auth(dm))
    ).json()["id"]

    created = await auth_client.post(
        f"/campaigns/{campaign_id}/characters", json=_THORA, headers=_auth(dm)
    )
    assert created.status_code == 201
    character = created.json()
    assert character["name"] == "Thora"
    assert character["player_id"] is not None

    fetched = await auth_client.get(f"/characters/{character['id']}", headers=_auth(dm))
    assert fetched.status_code == 200
    assert fetched.json()["sheet"]["abilities"]["str"] == 18


async def test_unknown_character_is_404(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    dm = mint_token(sub="clerk_dm7", email="dm7@example.com")
    resp = await auth_client.get(f"/characters/{uuid.uuid4()}", headers=_auth(dm))
    assert resp.status_code == 404


async def test_profile_and_red_lines_round_trip(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    dm = mint_token(sub="clerk_dm8", email="dm8@example.com")
    campaign_id = (
        await auth_client.post("/campaigns", json={"name": "Standin"}, headers=_auth(dm))
    ).json()["id"]
    character_id = (
        await auth_client.post(
            f"/campaigns/{campaign_id}/characters", json=_THORA, headers=_auth(dm)
        )
    ).json()["id"]

    set_profile = await auth_client.put(
        f"/characters/{character_id}/profile",
        json={"persona": "Blunt and brave.", "risk_tolerance": "bold"},
        headers=_auth(dm),
    )
    assert set_profile.status_code == 200
    got_profile = await auth_client.get(
        f"/characters/{character_id}/profile", headers=_auth(dm)
    )
    assert got_profile.json()["persona"] == "Blunt and brave."
    assert got_profile.json()["risk_tolerance"] == "bold"

    add_line = await auth_client.post(
        f"/characters/{character_id}/red-lines",
        json={"kind": "no_attacking_allies", "note": "never a party member"},
        headers=_auth(dm),
    )
    assert add_line.status_code == 201
    listed = await auth_client.get(
        f"/characters/{character_id}/red-lines", headers=_auth(dm)
    )
    assert [rl["kind"] for rl in listed.json()] == ["no_attacking_allies"]
    assert listed.json()[0]["note"] == "never a party member"


async def test_member_who_is_not_owner_cannot_edit_character(
    auth_client: httpx.AsyncClient, mint_token: Callable[..., str]
) -> None:
    dm = mint_token(sub="clerk_dm9", email="dm9@example.com")
    player = mint_token(sub="clerk_p3", email="player3@example.com")
    campaign_id = (
        await auth_client.post("/campaigns", json={"name": "Owned"}, headers=_auth(dm))
    ).json()["id"]
    # player joins the campaign
    token = (
        await auth_client.post(
            f"/campaigns/{campaign_id}/invites",
            json={"email": "player3@example.com"},
            headers=_auth(dm),
        )
    ).json()["token"]
    await auth_client.post(f"/invites/{token}/accept", headers=_auth(player))
    # DM creates a character they own
    character_id = (
        await auth_client.post(
            f"/campaigns/{campaign_id}/characters", json=_THORA, headers=_auth(dm)
        )
    ).json()["id"]

    # the player is a member (can read) but neither owner nor DM (cannot edit)
    assert (
        await auth_client.get(f"/characters/{character_id}", headers=_auth(player))
    ).status_code == 200
    forbidden = await auth_client.put(
        f"/characters/{character_id}/profile",
        json={"persona": "hijacked"},
        headers=_auth(player),
    )
    assert forbidden.status_code == 403
