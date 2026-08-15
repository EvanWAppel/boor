"""Shared pytest fixtures for the boor service test suite.

Per project conventions we DRY test setup via fixtures here.
"""

from __future__ import annotations

import random

import pytest
from fastapi.testclient import TestClient

from boor_service.api import app


@pytest.fixture
def rng() -> random.Random:
    """A seeded RNG so dice tests are deterministic and repeatable."""
    return random.Random(1234)


@pytest.fixture
def client() -> TestClient:
    """HTTP client bound to the FastAPI app for endpoint tests."""
    return TestClient(app)
