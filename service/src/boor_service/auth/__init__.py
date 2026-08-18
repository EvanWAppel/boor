"""Auth layer for boor: verify Clerk JWTs, mirror identities, gate by role (D-03).

The service is a Clerk *resource server* — it trusts the session JWT the web app
forwards, verified against Clerk's public JWKS (no Clerk secret lives here). This
package exposes the pure verifier (:mod:`.clerk`); the FastAPI dependencies live in
:mod:`.dependencies` and are imported directly by the API to avoid pulling FastAPI
into pure-verification contexts.
"""

from __future__ import annotations

from boor_service.auth.clerk import (
    AuthError,
    ClerkVerifier,
    VerifiedIdentity,
    verifier_from_env,
)

__all__ = [
    "AuthError",
    "ClerkVerifier",
    "VerifiedIdentity",
    "verifier_from_env",
]
