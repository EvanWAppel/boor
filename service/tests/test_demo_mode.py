"""PLAT-DEMO-01: the public, sign-in-free demo (``boor-demo.evanappel.me``).

A request whose ``Origin`` is the demo web host is a *demo request*. Demo mode can
only lower privilege: it reads and writes a separate ``boor_demo`` schema, never
the real tables; it bypasses Clerk only for synthetic guest users; it never calls
Anthropic. The real host keeps today's login, unchanged.

``demo_client`` (conftest) wires the real database to the test's public schema and
records every use of it, so each test can prove a demo request never touched it.
"""

from __future__ import annotations

import uuid
from typing import Any

import anthropic
import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from boor_service import demo_mode, guided_scenes
from boor_service.db import demo as demo_db
from boor_service.db.models import Campaign, User
from boor_service.realtime import WS_UNAUTHORIZED, SessionHub, handle_connection
from tests.conftest import DEMO_ORIGIN, RealDbProbe
from tests.test_guided import command
from tests.test_guided_adventure import fixed_check
from tests.test_realtime import FakeWebSocket

REAL_ORIGIN = "https://web-production-0e6881.up.railway.app"


def guest_token() -> str:
    return f"demo.{uuid.uuid4().hex}"


def demo_headers(token: str | None = None) -> dict[str, str]:
    headers = {"Origin": DEMO_ORIGIN}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _public_user_count(session: AsyncSession) -> int:
    await session.rollback()  # see the latest committed state
    return await session.scalar(select(func.count()).select_from(User)) or 0


# --- demo host: no login, demo data only ------------------------------------


async def test_demo_guest_needs_no_login_and_gets_a_seeded_campaign(
    demo_client: httpx.AsyncClient, real_db: RealDbProbe, session: AsyncSession
) -> None:
    token = guest_token()
    me = await demo_client.get("/me", headers=demo_headers(token))
    assert me.status_code == 200, me.text
    assert me.json()["email"].endswith("@demo.invalid")

    campaigns = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()
    assert len(campaigns) == 1 and campaigns[0]["my_role"] == "dm"
    sessions = (
        await demo_client.get(
            f"/campaigns/{campaigns[0]['id']}/sessions", headers=demo_headers(token)
        )
    ).json()
    assert [s["status"] for s in sessions] == ["active"]

    assert real_db.uses == 0
    assert await _public_user_count(session) == 0


async def test_each_guest_gets_their_own_sandbox(demo_client: httpx.AsyncClient) -> None:
    a, b = guest_token(), guest_token()
    camp_a = (await demo_client.get("/campaigns", headers=demo_headers(a))).json()[0]["id"]
    camp_b = (await demo_client.get("/campaigns", headers=demo_headers(b))).json()[0]["id"]
    assert camp_a != camp_b
    # A guest can't reach another guest's campaign.
    peek = await demo_client.get(f"/campaigns/{camp_a}/members", headers=demo_headers(b))
    assert peek.status_code == 403


async def test_the_same_guest_token_returns_the_same_sandbox(
    demo_client: httpx.AsyncClient,
) -> None:
    token = guest_token()
    first = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()
    again = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()
    assert first == again


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer not-a-guest", "Bearer demo.xyz", "Bearer demo.ABCDEF"],
)
async def test_demo_rejects_missing_or_malformed_guest_tokens(
    demo_client: httpx.AsyncClient, real_db: RealDbProbe, authorization: str | None
) -> None:
    headers = {"Origin": DEMO_ORIGIN}
    if authorization:
        headers["Authorization"] = authorization
    assert (await demo_client.get("/me", headers=headers)).status_code == 401
    assert real_db.uses == 0


async def test_demo_ignores_a_real_clerk_token(
    demo_client: httpx.AsyncClient, real_db: RealDbProbe, mint_token: Any
) -> None:
    # A valid Clerk session on the demo host grants nothing: Clerk isn't consulted.
    token = mint_token(sub="clerk_real", email="real@example.com")
    assert (await demo_client.get("/me", headers=demo_headers(token))).status_code == 401
    assert real_db.uses == 0


async def test_guest_cap_refuses_new_sandboxes(
    demo_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MAX_GUESTS", "1")
    assert (await demo_client.get("/me", headers=demo_headers(guest_token()))).status_code == 200
    full = await demo_client.get("/me", headers=demo_headers(guest_token()))
    assert full.status_code == 503
    assert "demo" in full.json()["detail"].lower()


# --- writes: inside the guest's own campaign only ---------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/campaigns", {"name": "Another"}),
        ("POST", "/campaigns/{campaign}/invites", {"email": "someone@example.com"}),
        ("POST", "/invites/sometoken/accept", None),
    ],
)
async def test_demo_blocks_writes_outside_the_sandbox(
    demo_client: httpx.AsyncClient, method: str, path: str, body: Any
) -> None:
    token = guest_token()
    campaign = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()[0]["id"]
    resp = await demo_client.request(
        method, path.format(campaign=campaign), json=body, headers=demo_headers(token)
    )
    assert resp.status_code == 403
    assert "demo" in resp.json()["detail"].lower()


async def test_guest_plays_the_guided_adventure_solo(
    demo_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    token = guest_token()
    campaign = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()[0]["id"]
    game = (
        await demo_client.get(f"/campaigns/{campaign}/sessions", headers=demo_headers(token))
    ).json()[0]["id"]
    path = f"/sessions/{game}/guided"

    async def act(action: str, rev: int, **extra: Any) -> dict[str, Any]:
        r = await demo_client.post(
            path, json=command(action, rev, **extra), headers=demo_headers(token)
        )
        assert r.status_code == 200, r.text
        return r.json()["state"]

    state = await act("start", 0)
    state = await act("select", state["revision"], pregen="guardian")
    state = await act("ready", state["revision"])
    state = await act("begin", state["revision"])
    assert state["scene"] == "cart"
    state = await act("approach", state["revision"], approach="lift")
    state = await act("roll", state["revision"])
    assert state["result"]["success"] is True


# --- demo host never spends money --------------------------------------------


@pytest.fixture
def anthropic_tripwire(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every AI flag on, a key present, and a record of any Anthropic client built."""
    monkeypatch.setenv("ENABLE_AI_ADJUDICATION", "1")
    monkeypatch.setenv("ENABLE_STANDINS", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    built: list[Any] = []

    def _tripwire(*args: Any, **kwargs: Any) -> Any:
        built.append((args, kwargs))
        raise AssertionError("demo request built an Anthropic client")

    monkeypatch.setattr(anthropic, "Anthropic", _tripwire)
    return built


async def test_demo_never_calls_anthropic_even_with_ai_enabled(
    demo_client: httpx.AsyncClient,
    anthropic_tripwire: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    token = guest_token()
    campaign = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()[0]["id"]
    game = (
        await demo_client.get(f"/campaigns/{campaign}/sessions", headers=demo_headers(token))
    ).json()[0]["id"]
    characters = (
        await demo_client.get(f"/campaigns/{campaign}/characters", headers=demo_headers(token))
    ).json()
    path = f"/sessions/{game}/guided"

    async def act(action: str, rev: int, **extra: Any) -> dict[str, Any]:
        r = await demo_client.post(
            path, json=command(action, rev, **extra), headers=demo_headers(token)
        )
        assert r.status_code == 200, r.text
        return r.json()["state"]

    state = await act("start", 0)
    state = await act("select", state["revision"], pregen="guardian")
    state = await act("ready", state["revision"])
    state = await act("begin", state["revision"])
    # A free-form proposal is what would reach the AI guide; in the demo the host decides.
    state = await act("propose", state["revision"], text="Wedge rocks under the wheel")
    assert state["proposal"]["text"] == "Wedge rocks under the wheel"

    # Stand-in turns are refused outright on the demo host.
    character = characters[0]["id"]
    turn = await demo_client.post(
        f"/sessions/{game}/standins/{character}/turn",
        json={"request_id": str(uuid.uuid4())},
        headers=demo_headers(token),
    )
    assert turn.status_code == 503

    # Ending the session would queue recaps; none may call the model.
    ended = await demo_client.post(f"/sessions/{game}/end", headers=demo_headers(token))
    assert ended.status_code == 200, ended.text

    assert anthropic_tripwire == []


# --- real host: login exactly as before ---------------------------------------


async def test_real_host_still_requires_a_clerk_login(demo_client: httpx.AsyncClient) -> None:
    for headers in ({}, {"Origin": REAL_ORIGIN}):
        assert (await demo_client.get("/me", headers=headers)).status_code == 401
    # A guest token is not a credential on the real host.
    guest = {"Origin": REAL_ORIGIN, "Authorization": f"Bearer {guest_token()}"}
    assert (await demo_client.get("/me", headers=guest)).status_code == 401


async def test_real_host_clerk_login_uses_the_real_database(
    demo_client: httpx.AsyncClient, real_db: RealDbProbe, mint_token: Any, session: AsyncSession
) -> None:
    token = mint_token(sub="clerk_real", email="real@example.com", name="Real")
    resp = await demo_client.get(
        "/me", headers={"Origin": REAL_ORIGIN, "Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "real@example.com"
    assert real_db.uses > 0
    assert await _public_user_count(session) == 1


async def test_demo_origin_is_allowed_by_cors(demo_client: httpx.AsyncClient) -> None:
    preflight = await demo_client.options(
        "/me",
        headers={
            "Origin": DEMO_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert preflight.headers.get("access-control-allow-origin") == DEMO_ORIGIN


# --- detection + local switch -------------------------------------------------


def test_demo_detection_by_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOOR_DEMO", raising=False)
    monkeypatch.delenv("DEMO_ORIGINS", raising=False)
    assert demo_mode.is_demo_origin(DEMO_ORIGIN)
    assert not demo_mode.is_demo_origin(REAL_ORIGIN)
    assert not demo_mode.is_demo_origin(None)
    monkeypatch.setenv("DEMO_ORIGINS", "http://localhost:3001")
    assert demo_mode.is_demo_origin("http://localhost:3001")
    assert not demo_mode.is_demo_origin(DEMO_ORIGIN)


def test_local_switch_is_off_by_default_and_forces_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOOR_DEMO", raising=False)
    assert not demo_mode.is_demo_origin("http://localhost:3000")
    monkeypatch.setenv("BOOR_DEMO", "1")
    assert demo_mode.is_demo_origin("http://localhost:3000")
    assert demo_mode.is_demo_origin(None)


def test_no_demo_context_outside_a_request() -> None:
    assert demo_mode.active() is False


# --- realtime -----------------------------------------------------------------


async def test_demo_websocket_accepts_a_guest_and_rejects_clerk(
    demo_client: httpx.AsyncClient, clerk_verifier: Any, mint_token: Any, real_db: RealDbProbe
) -> None:
    token = guest_token()
    campaign = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()[0]["id"]
    game = uuid.UUID(
        (
            await demo_client.get(f"/campaigns/{campaign}/sessions", headers=demo_headers(token))
        ).json()[0]["id"]
    )
    with demo_mode.activated():
        async with demo_db.sessionmaker()() as db:
            ok = FakeWebSocket(token=token, incoming=[{"type": "chat", "body": "hello"}])
            await handle_connection(ok, game, db, clerk_verifier, SessionHub())
            assert ok.close_code is None
            assert any(m.get("type") == "chat" for m in ok.sent)

            clerk = FakeWebSocket(token=mint_token(sub="clerk_ws", email="ws@example.com"))
            await handle_connection(clerk, game, db, clerk_verifier, SessionHub())
            assert clerk.close_code == WS_UNAUTHORIZED
    assert real_db.uses == 0


# --- reset ----------------------------------------------------------------------


async def test_reset_wipes_every_sandbox(demo_client: httpx.AsyncClient) -> None:
    token = guest_token()
    before = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()[0]["id"]
    await demo_db.reset()
    async with demo_db.sessionmaker()() as db:
        assert await db.scalar(select(func.count()).select_from(Campaign)) == 0
    # The same browser comes back to a fresh sandbox.
    after = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()[0]["id"]
    assert after != before


async def test_sandbox_resets_once_it_is_older_than_the_period(
    demo_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = guest_token()
    before = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()[0]["id"]
    monkeypatch.setenv("DEMO_RESET_HOURS", "0")
    after = (await demo_client.get("/campaigns", headers=demo_headers(token))).json()[0]["id"]
    assert after != before
