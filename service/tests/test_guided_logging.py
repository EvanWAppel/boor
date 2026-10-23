"""X-01: one structured log record per guided command.

Each command on ``POST /sessions/{id}/guided`` logs exactly one record on
``boor_service.guided`` with the run (game session) id, request id, scene, phase,
command, submitted revision and outcome; a rejection also carries its HTTP status
and the reason. Bearer tokens and free-form text (proposals, notes) never appear.
"""

from __future__ import annotations

import logging

import pytest

from boor_service import guided_ai
from boor_service.guided import GuidedCommandLog
from tests.test_guided import command
from tests.test_guided_gaps import _two_player_party
from tests.test_session_api import _auth

LOGGER = "boor_service.guided"


def _records(caplog: pytest.LogCaptureFixture) -> list[GuidedCommandLog]:
    return [
        r.guided_command  # type: ignore[attr-defined]
        for r in caplog.records
        if r.name == LOGGER and hasattr(r, "guided_command")
    ]


async def test_accepted_command_logs_one_record_without_text_or_token(
    auth_client, mint_token, caplog, monkeypatch
):
    monkeypatch.setattr(guided_ai, "get_client", lambda: None)
    path, host, player, state, _act = await _two_player_party(auth_client, mint_token)
    caplog.set_level(logging.INFO, logger=LOGGER)
    secret = "SECRET-PROPOSAL-TEXT wedge rocks under the wheel"
    body = command("propose", state["revision"], text=secret)

    r = await auth_client.post(path + "/guided", headers=_auth(player), json=body)
    assert r.status_code == 200, r.text

    [record] = _records(caplog)
    assert record.session_id == path.split("/")[-1]
    assert record.request_id == body["request_id"]
    assert record.action == "propose"
    assert record.scene == "cart"
    assert record.revision == state["revision"]
    assert record.outcome == "accepted"
    assert record.new_revision == state["revision"] + 1
    assert record.status == 200 and record.reason is None
    assert secret not in caplog.text and "SECRET" not in caplog.text
    assert player not in caplog.text and host not in caplog.text
    assert "outcome=accepted" in caplog.text and "action=propose" in caplog.text


async def test_rejected_command_logs_status_and_reason(auth_client, mint_token, caplog):
    path, _host, player, state, _act = await _two_player_party(auth_client, mint_token)
    caplog.set_level(logging.INFO, logger=LOGGER)
    stale = command("propose", state["revision"] - 1, text="SECRET-STALE-TEXT")

    r = await auth_client.post(path + "/guided", headers=_auth(player), json=stale)
    assert r.status_code == 409

    [record] = _records(caplog)
    assert record.outcome == "rejected"
    assert record.status == 409
    assert record.reason is not None and "moved on" in record.reason
    assert record.action == "propose"
    assert record.scene == "cart"
    assert record.revision == state["revision"] - 1
    assert record.new_revision is None
    assert "SECRET" not in caplog.text and player not in caplog.text
    assert "outcome=rejected" in caplog.text


async def test_retried_command_logs_as_replayed(auth_client, mint_token, caplog):
    path, host, _player, state, _act = await _two_player_party(auth_client, mint_token)
    caplog.set_level(logging.INFO, logger=LOGGER)
    body = command("pause", state["revision"])
    first = await auth_client.post(path + "/guided", headers=_auth(host), json=body)
    assert first.status_code == 200, first.text
    again = await auth_client.post(path + "/guided", headers=_auth(host), json=body)
    assert again.status_code == 200

    assert [r.outcome for r in _records(caplog)] == ["accepted", "replayed"]
