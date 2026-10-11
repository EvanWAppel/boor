"""v5 free-form ideas: a proposal that fits no offered approach becomes its own check.

Decided by Evan 2026-10-10: check scenes only; any SRD skill at Easy 10 / Medium 12 /
Hard 15; success and failure use the scene's authored outcome (so the story graph is
unchanged); the AI guide and the host may both create one, and the host wins.
"""

from boor_service import guided_scenes
from boor_service.ai.adjudicator import Adjudication
from tests.test_guided import command
from tests.test_guided_adventure import _me, begin, fixed_check
from tests.test_guided_ai import last_guide_event, latest
from tests.test_guided_proposals_scenes import _to_mara
from tests.test_session_api import _auth


async def post(client, path, token, action, rev, **extra):
    return await client.post(
        path + "/guided", headers=_auth(token), json=command(action, rev, **extra)
    )


async def test_host_runs_an_idea_as_its_own_check_with_the_scenes_outcome(
    auth_client, mint_token, monkeypatch
):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    proposed = await act(player, "propose", state["revision"], text="Coax the mule to pull")
    checked = await act(
        host,
        "custom_check",
        proposed["revision"],
        skill="animal_handling",
        dc=15,
        text="A calm voice might get the mule moving.",
    )
    assert checked["proposal"] is None and checked["phase"] == "check"
    pending = checked["pending"]
    assert pending["user_id"] == await _me(auth_client, player)
    assert pending["skill"] == "animal_handling" and pending["dc"] == 15
    assert "Coax the mule to pull" in pending["label"]
    log = (await auth_client.get(path + "/log", headers=_auth(host))).json()
    assert "A calm voice might get the mule moving." in log[-1]["body"]
    rolled = await act(player, "roll", checked["revision"])
    # The scene's own authored success: the story continues exactly as before.
    assert rolled["result"]["success"] is True
    assert rolled["result"]["outcome"] == guided_scenes.CHECK_SCENES["cart"].success
    assert rolled["result"]["dc"] == 15


async def test_custom_check_bounds_and_permissions(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    rev = (await act(player, "propose", state["revision"], text="Something clever"))["revision"]
    for bad in (
        {"skill": "flying", "dc": 12},  # not an SRD skill
        {"skill": "stealth", "dc": 13},  # not one of the three difficulties
        {"skill": "stealth"},  # difficulty required
    ):
        assert (await post(auth_client, path, host, "custom_check", rev, **bad)).status_code == 422
    # Only the host may create one.
    assert (
        await post(auth_client, path, player, "custom_check", rev, skill="stealth", dc=12)
    ).status_code == 403
    # The proposal is still open after the rejected attempts.
    assert (await latest(auth_client, path, host))["proposal"]["text"] == "Something clever"


async def test_no_custom_check_outside_check_scenes(auth_client, mint_token, monkeypatch):
    path, host, player, state, act = await _to_mara(auth_client, mint_token, monkeypatch)
    proposed = await act(player, "propose", state["revision"], text="Read her face")
    assert (
        await post(
            auth_client, path, host, "custom_check", proposed["revision"], skill="insight", dc=10
        )
    ).status_code == 409


async def test_ai_guide_creates_a_bounded_check(
    auth_client, mint_token, monkeypatch, fake_adjudicator
):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(1))
    fake_adjudicator.result = Adjudication(
        approach=None, reason="Sneaking past is fair.", skill="stealth", dc=10
    )
    path, host, player, state, act = await begin(auth_client, mint_token)
    await act(player, "propose", state["revision"], text="Slip around and push from behind")
    assert fake_adjudicator.calls[0].allow_custom_check is True
    resolved = await latest(auth_client, path, host)
    assert resolved["phase"] == "check"
    assert resolved["pending"]["skill"] == "stealth" and resolved["pending"]["dc"] == 10
    event = await last_guide_event(auth_client, path, host)
    assert event["actor_label"] == "AI guide" and "Sneaking past is fair." in event["body"]
    rolled = await act(player, "roll", resolved["revision"])
    assert rolled["result"]["success"] is False
    assert rolled["result"]["outcome"] == guided_scenes.CHECK_SCENES["cart"].failure


async def test_ai_guide_is_not_offered_custom_checks_outside_check_scenes(
    auth_client, mint_token, monkeypatch, fake_adjudicator
):
    fake_adjudicator.result = Adjudication(approach="mara", reason="About her cargo.")
    _path, _host, player, state, act = await _to_mara(auth_client, mint_token, monkeypatch)
    await act(player, "propose", state["revision"], text="What's in the crates?")
    assert fake_adjudicator.calls[0].allow_custom_check is False
