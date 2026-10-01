"""v5 AI guide: adjudicates "try something else" proposals; the host can override.

The model call runs as a background task after the proposal is saved. On any
failure the proposal stays open for the host — nothing is silently resolved.
"""

import anthropic
import httpx

from boor_service import guided_scenes
from boor_service.ai.adjudicator import Adjudication, AdjudicationError
from tests.test_guided import command
from tests.test_guided_adventure import begin, fixed_check
from tests.test_session_api import _auth


async def latest(client, path, token):
    return (await client.get(path + "/guided", headers=_auth(token))).json()["state"]


async def last_guide_event(client, path, token):
    log = (await client.get(path + "/log", headers=_auth(token))).json()
    return [e for e in log if e["kind"] == "narration"][-1]


async def test_ai_maps_proposal_and_proposer_rolls(
    auth_client, mint_token, monkeypatch, fake_adjudicator
):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    fake_adjudicator.result = Adjudication(approach="leverage", reason="A plank is a lever.")
    path, host, player, state, act = await begin(auth_client, mint_token)
    proposed = await act(player, "propose", state["revision"], text="Wedge a plank under it")
    # The propose response returns at once, flagged as being considered by the AI guide.
    assert proposed["proposal"]["ai"] == "thinking"
    ctx = fake_adjudicator.calls[0]
    assert ctx.proposal == "Wedge a plank under it"
    assert [a["id"] for a in ctx.approaches] == ["lift", "leverage"]

    resolved = await latest(auth_client, path, host)
    assert resolved["proposal"] is None and resolved["phase"] == "check"
    me = (await auth_client.get("/me", headers=_auth(player))).json()["id"]
    assert resolved["pending"]["user_id"] == me
    assert resolved["pending"]["skill"] == "investigation"
    event = await last_guide_event(auth_client, path, host)
    assert event["actor_label"] == "AI guide"
    assert event["payload"]["ai_adjudicated"] is True
    assert "A plank is a lever." in event["body"]
    rolled = await act(player, "roll", resolved["revision"])
    assert rolled["result"]["success"] is True


async def test_ai_declines_with_reason(auth_client, mint_token, fake_adjudicator):
    fake_adjudicator.result = Adjudication(approach=None, reason="No magic here; try a lever.")
    path, host, player, state, act = await begin(auth_client, mint_token)
    await act(player, "propose", state["revision"], text="I cast fly on the cart")
    resolved = await latest(auth_client, path, host)
    assert resolved["proposal"] is None and resolved["phase"] == "ready"
    event = await last_guide_event(auth_client, path, host)
    assert "No magic here; try a lever." in event["body"]
    assert "I cast fly on the cart" in event["body"]


async def test_ai_failure_falls_back_to_host(auth_client, mint_token, fake_adjudicator):
    for failure in [
        AdjudicationError("refused"),
        TimeoutError(),
        anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")),
    ]:
        fake_adjudicator.result = failure
        path, host, player, state, act = await begin(auth_client, mint_token)
        await act(player, "propose", state["revision"], text="Ask a passer-by for help")
        open_ = await latest(auth_client, path, host)
        # The proposal stays open, marked so the table knows the host will respond.
        assert open_["proposal"]["text"] == "Ask a passer-by for help"
        assert open_["proposal"]["ai"] == "unavailable"
        accepted = await act(host, "accept_proposal", open_["revision"], approach="lift")
        assert accepted["phase"] == "check"


async def test_host_overrides_while_ai_thinks(auth_client, mint_token, fake_adjudicator):
    path, host, player, state, act = await begin(auth_client, mint_token)
    revision = state["revision"] + 1  # after the propose event

    async def host_declines_first():
        r = await auth_client.post(
            path + "/guided",
            headers=_auth(host),
            json=command("decline_proposal", revision, text="Not here — try lifting."),
        )
        assert r.status_code == 200, r.text

    fake_adjudicator.before = host_declines_first
    fake_adjudicator.result = Adjudication(approach="lift", reason="Fits.")
    await act(player, "propose", state["revision"], text="Something odd")
    final = await latest(auth_client, path, host)
    # The host's answer stands; the late AI decision is discarded, not applied on top.
    assert final["proposal"] is None and final["phase"] == "ready"
    assert final["pending"] is None
    assert final["revision"] == revision + 1


async def test_pause_while_ai_thinks_hands_back_to_host(auth_client, mint_token, fake_adjudicator):
    path, host, player, state, act = await begin(auth_client, mint_token)
    revision = state["revision"] + 1

    async def pause_first():
        r = await auth_client.post(
            path + "/guided", headers=_auth(player), json=command("pause", revision)
        )
        assert r.status_code == 200, r.text

    fake_adjudicator.before = pause_first
    await act(player, "propose", state["revision"], text="Something odd")
    final = await latest(auth_client, path, host)
    # A pause freezes game actions, including the AI's: the proposal waits for the host.
    assert final["paused"] is not None
    assert final["proposal"]["ai"] == "unavailable"
    assert final["pending"] is None


async def test_ai_disabled_keeps_plain_host_handoff(auth_client, mint_token):
    _path, _host, player, state, act = await begin(auth_client, mint_token)
    proposed = await act(player, "propose", state["revision"], text="Anything")
    assert proposed["proposal"].get("ai") is None
