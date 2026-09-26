"""Clerk JWT verification via JWKS (AUTH-01, decision D-03).

The service is a resource server: the Next.js app authenticates the user with
Clerk and forwards the resulting session JWT as a ``Bearer`` token. We verify that
token against Clerk's **public** JWKS (RS256) — no Clerk secret key lives here — and
extract the identity. Clerk must be configured with a JWT template that exposes the
user's ``email`` (and ideally ``name``); ``sub`` is always the Clerk user id.

The signing-key resolver is injected so verification is unit-testable with a local
keypair and never touches the network. Bad tokens raise :class:`AuthError`; per
project convention we surface the real reason rather than swallowing it.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

_ALGORITHMS = ["RS256"]
#: Small clock-skew tolerance for exp/nbf/iat checks.
_LEEWAY_SECONDS = 30


class AuthError(Exception):
    """A token was missing, malformed, expired, or failed verification."""


@dataclass(frozen=True)
class VerifiedIdentity:
    """The trusted identity extracted from a verified Clerk token."""

    clerk_user_id: str
    email: str | None
    display_name: str | None


#: Resolves the RSA signing key for a given token's ``kid`` (injectable for tests).
#: Returns whatever ``jwt.decode`` accepts as a key — a public-key object or PEM.
SigningKeyResolver = Callable[[str], Any]


class ClerkVerifier:
    """Verifies Clerk session JWTs and returns the identity they assert."""

    def __init__(
        self,
        *,
        issuer: str,
        signing_key_resolver: SigningKeyResolver,
        audience: str | None = None,
        email_claim: str = "email",
        name_claim: str = "name",
    ) -> None:
        self._issuer = issuer
        self._resolve_key = signing_key_resolver
        self._audience = audience
        self._email_claim = email_claim
        self._name_claim = name_claim

    def verify(self, token: str) -> VerifiedIdentity:
        """Verify ``token``'s signature, issuer, and expiry; return its identity.

        Raises :class:`AuthError` on any failure (bad signature, wrong issuer,
        expired, or a missing ``sub``).
        """
        try:
            signing_key = self._resolve_key(token)
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=_ALGORITHMS,
                issuer=self._issuer,
                audience=self._audience,
                leeway=_LEEWAY_SECONDS,
                options={
                    "require": ["exp", "iat", "sub"],
                    "verify_aud": self._audience is not None,
                },
            )
        except jwt.PyJWTError as exc:
            # Includes ExpiredSignatureError, InvalidIssuerError, InvalidSignatureError.
            raise AuthError(f"token verification failed: {exc}") from exc

        subject = claims.get("sub")
        if not subject:
            raise AuthError("token has no subject (sub) claim")

        return VerifiedIdentity(
            clerk_user_id=subject,
            email=claims.get(self._email_claim),
            display_name=claims.get(self._name_claim),
        )


def _jwks_resolver(jwks_url: str) -> SigningKeyResolver:
    """A caching JWKS-backed resolver: fetch Clerk's public keys, pick by ``kid``."""
    client = PyJWKClient(jwks_url)

    def resolve(token: str) -> Any:
        return client.get_signing_key_from_jwt(token).key

    return resolve


@lru_cache(maxsize=1)
def verifier_from_env() -> ClerkVerifier:
    """Build the process-wide verifier from ``CLERK_*`` environment variables.

    Requires ``CLERK_ISSUER`` and ``CLERK_JWKS_URL`` (Railway provides them);
    ``CLERK_AUDIENCE`` is optional. Raises loudly if the required config is absent —
    we do not silently run an unauthenticated service.
    """
    issuer = os.environ.get("CLERK_ISSUER")
    jwks_url = os.environ.get("CLERK_JWKS_URL")
    if not issuer or not jwks_url:
        raise RuntimeError(
            "CLERK_ISSUER and CLERK_JWKS_URL must be set to verify Clerk tokens"
        )
    return ClerkVerifier(
        issuer=issuer,
        signing_key_resolver=_jwks_resolver(jwks_url),
        audience=os.environ.get("CLERK_AUDIENCE"),
    )
