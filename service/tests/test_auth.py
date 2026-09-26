"""Tests for Clerk auth: token verification, the user mirror, and role gating.

Verification is exercised with a *local* RSA keypair and an injected signing-key
resolver, so no network or real Clerk instance is touched — the same seam the
production JWKS resolver plugs into. The DB-backed pieces (user mirror, membership
gating) run against the ephemeral testcontainers Postgres and call the FastAPI
dependencies directly, sidestepping TestClient event-loop juggling.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from boor_service.auth import dependencies as deps
from boor_service.auth.clerk import AuthError, ClerkVerifier
from boor_service.db.models import MembershipRole, User
from boor_service.db.repository import (
    accept_invite,
    create_campaign_with_owner,
    invite_player,
    sync_user,
)

ISSUER = "https://clerk.example.test"

UserFactory = Callable[..., Awaitable[User]]


def _keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


# Generated once for the module: a primary keypair, plus a stray key for the
# bad-signature case (RSA keygen is comparatively slow).
_PRIVATE_PEM, _PUBLIC_PEM = _keypair()
_OTHER_PRIVATE_PEM, _ = _keypair()


def _verifier(*, public_pem: str = _PUBLIC_PEM, audience: str | None = None) -> ClerkVerifier:
    return ClerkVerifier(
        issuer=ISSUER,
        signing_key_resolver=lambda _token: public_pem,
        audience=audience,
    )


def _mint(
    *,
    private_pem: str = _PRIVATE_PEM,
    sub: str | None = "clerk_user_1",
    iss: str = ISSUER,
    email: str | None = "ada@example.com",
    name: str | None = "Ada",
    exp_delta: int = 3600,
    omit: tuple[str, ...] = (),
) -> str:
    now = int(time.time())
    claims: dict[str, object] = {"iat": now, "exp": now + exp_delta, "iss": iss}
    if sub is not None:
        claims["sub"] = sub
    if email is not None:
        claims["email"] = email
    if name is not None:
        claims["name"] = name
    for key in omit:
        claims.pop(key, None)
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test"})


def _request(token: str | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request(
        {"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": headers}
    )


# --- ClerkVerifier (pure, local keypair) -----------------------------------


def test_verify_valid_token_returns_identity() -> None:
    identity = _verifier().verify(_mint())
    assert identity.clerk_user_id == "clerk_user_1"
    assert identity.email == "ada@example.com"
    assert identity.display_name == "Ada"


def test_verify_token_without_email_has_none_email() -> None:
    identity = _verifier().verify(_mint(email=None))
    assert identity.clerk_user_id == "clerk_user_1"
    assert identity.email is None


def test_expired_token_rejected() -> None:
    with pytest.raises(AuthError):
        _verifier().verify(_mint(exp_delta=-3600))


def test_wrong_issuer_rejected() -> None:
    with pytest.raises(AuthError):
        _verifier().verify(_mint(iss="https://evil.example"))


def test_bad_signature_rejected() -> None:
    # signed by a different key than the verifier trusts
    with pytest.raises(AuthError):
        _verifier().verify(_mint(private_pem=_OTHER_PRIVATE_PEM))


def test_missing_subject_rejected() -> None:
    with pytest.raises(AuthError):
        _verifier().verify(_mint(omit=("sub",)))


def test_audience_enforced_when_configured() -> None:
    verifier = _verifier(audience="boor-api")
    with pytest.raises(AuthError):
        verifier.verify(_mint())  # no aud claim -> rejected


# --- sync_user: the Clerk -> local mirror ----------------------------------


async def test_sync_user_creates_then_reuses(session: AsyncSession) -> None:
    first = await sync_user(
        session, clerk_user_id="clerk_x", email="x@example.com", display_name="X"
    )
    second = await sync_user(
        session, clerk_user_id="clerk_x", email="x@example.com", display_name="X"
    )
    assert first.id == second.id
    count = (
        await session.execute(
            select(func.count()).select_from(User).where(User.clerk_user_id == "clerk_x")
        )
    ).scalar_one()
    assert count == 1


async def test_sync_user_refreshes_email_and_name(session: AsyncSession) -> None:
    user = await sync_user(session, clerk_user_id="clerk_y", email="old@example.com")
    refreshed = await sync_user(
        session, clerk_user_id="clerk_y", email="new@example.com", display_name="Renamed"
    )
    assert refreshed.id == user.id
    assert refreshed.email == "new@example.com"
    assert refreshed.display_name == "Renamed"


async def test_sync_user_without_email_raises(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="without an email"):
        await sync_user(session, clerk_user_id="clerk_z", email=None)


# --- get_current_user dependency -------------------------------------------


async def test_get_current_user_mirrors_from_token(session: AsyncSession) -> None:
    token = _mint(sub="clerk_dm", email="dm@example.com", name="The DM")
    user = await deps.get_current_user(_request(token), session=session, verifier=_verifier())
    assert user.clerk_user_id == "clerk_dm"
    assert user.email == "dm@example.com"


async def test_missing_bearer_token_is_401(session: AsyncSession) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(_request(None), session=session, verifier=_verifier())
    assert exc_info.value.status_code == 401


async def test_invalid_token_is_401(session: AsyncSession) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(
            _request(_mint(exp_delta=-3600)), session=session, verifier=_verifier()
        )
    assert exc_info.value.status_code == 401


# --- role gating: current_membership / require_dm --------------------------


async def test_current_membership_returns_dm_for_owner(session: AsyncSession) -> None:
    owner = await deps.get_current_user(
        _request(_mint(sub="clerk_owner", email="owner@example.com")),
        session=session,
        verifier=_verifier(),
    )
    campaign = await create_campaign_with_owner(session, name="Table", owner=owner)

    membership = await deps.current_membership(campaign.id, user=owner, session=session)
    assert membership.role is MembershipRole.dm


async def test_non_member_is_403(session: AsyncSession, make_user: UserFactory) -> None:
    owner = await make_user()
    outsider = await make_user()
    campaign = await create_campaign_with_owner(session, name="Closed", owner=owner)

    with pytest.raises(HTTPException) as exc_info:
        await deps.current_membership(campaign.id, user=outsider, session=session)
    assert exc_info.value.status_code == 403


async def test_require_dm_rejects_a_player(
    session: AsyncSession, make_user: UserFactory
) -> None:
    owner = await make_user()
    player = await make_user()
    campaign = await create_campaign_with_owner(session, name="Party", owner=owner)
    invite = await invite_player(
        session, campaign=campaign, email=player.email, invited_by=owner
    )
    player_membership = await accept_invite(session, token=invite.token, user=player)

    # a player passes current_membership but is refused by require_dm
    assert player_membership.role is MembershipRole.player
    with pytest.raises(HTTPException) as exc_info:
        await deps.require_dm(player_membership)
    assert exc_info.value.status_code == 403


async def test_require_dm_allows_the_dm(session: AsyncSession, make_user: UserFactory) -> None:
    owner = await make_user()
    campaign = await create_campaign_with_owner(session, name="Mine", owner=owner)
    dm_membership = await deps.current_membership(campaign.id, user=owner, session=session)

    assert await deps.require_dm(dm_membership) is dm_membership
