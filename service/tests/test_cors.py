"""CORS lets the browser web app (a different origin in production) call the
service. Bearer tokens ride the Authorization header, so credentials are off and
an explicit origin allowlist suffices. These tests use a bare client (no DB) since
CORS is enforced ahead of routing/auth.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from boor_service.api import app

client = TestClient(app)

# The default allowlist (no CORS_ALLOW_ORIGINS set) is the local Next dev origin.
_ALLOWED = "http://localhost:3000"


def test_preflight_allows_configured_origin() -> None:
    resp = client.options(
        "/campaigns",
        headers={
            "Origin": _ALLOWED,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == _ALLOWED


def test_simple_request_echoes_allowed_origin() -> None:
    resp = client.get("/health", headers={"Origin": _ALLOWED})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == _ALLOWED


def test_unlisted_origin_is_not_allowed() -> None:
    resp = client.get("/health", headers={"Origin": "https://evil.example"})
    # The request still runs; it just isn't granted a cross-origin allow header,
    # so the browser blocks the response.
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
