"""v5 'try something else': a free-form proposal the host accepts or declines.

The proposal text is always preserved in the log and never silently resolved.
"""

from boor_service import guided_scenes
from tests.test_guided import command
from tests.test_guided_adventure import begin, fixed_check
from tests.test_session_api import _auth


async def post(client, path, token, action, rev, **extra):
    return await client.post(
        path + "/guided", headers=_auth(token), json=command(action, rev, **extra)
    )


async def test_propose_then_host_accepts_and_proposer_rolls(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    # A playing character proposes a free-form action at the cart.
    proposed = await act(player, "propose", state["revision"], text="Wedge rocks under the wheel")
    assert proposed["proposal"]["text"] == "Wedge rocks under the wheel"
    assert proposed["phase"] == "ready" and proposed["pending"] is None
    # While a proposal is open, a normal approach is blocked to avoid racing the host.
    assert (await post(auth_client, path, player, "approach", proposed["revision"],
                       approach="lift")).status_code == 409
    # Only the host may respond, and must map it to an offered approach.
    assert (await post(auth_client, path, player, "accept_proposal", proposed["revision"],
                       approach="lift")).status_code == 403
    accepted = await act(host, "accept_proposal", proposed["revision"], approach="lift")
    assert accepted["proposal"] is None
    assert accepted["phase"] == "check"
    # The proposer becomes the designated roller.
    me = (await auth_client.get("/me", headers=_auth(player))).json()["id"]
    assert accepted["pending"]["user_id"] == me
    assert accepted["pending"]["skill"] == "athletics"
    rolled = await act(player, "roll", accepted["revision"])
    assert rolled["result"]["success"] is True


async def test_propose_then_host_declines_reopens_actions(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    proposed = await act(player, "propose", state["revision"], text="Fly the cart across")
    # Empty reason is rejected; the text is never silently dropped.
    assert (await post(auth_client, path, host, "decline_proposal", proposed["revision"],
                       text="  ")).status_code == 422
    declined = await act(host, "decline_proposal", proposed["revision"],
                         text="No magic here; try lifting or leverage.")
    assert declined["proposal"] is None and declined["phase"] == "ready"
    # After a decline the offered actions work again.
    approached = await act(player, "approach", declined["revision"], approach="leverage")
    assert approached["pending"]["skill"] == "investigation"


async def test_proposal_guards(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    # The watching host holds no character, so cannot propose.
    assert (await post(auth_client, path, host, "propose", state["revision"],
                       text="something")).status_code == 409
    # Empty proposal text is rejected.
    assert (await post(auth_client, path, player, "propose", state["revision"],
                       text="   ")).status_code == 422
    proposed = await act(player, "propose", state["revision"], text="Ask a passer-by for help")
    # Only one open proposal at a time.
    assert (await post(auth_client, path, player, "propose", proposed["revision"],
                       text="another")).status_code == 409
    # Accepting requires a valid offered approach.
    assert (await post(auth_client, path, host, "accept_proposal", proposed["revision"],
                       approach="not-real")).status_code == 422
    # The proposal survives a refresh (persisted, replayable).
    replay = (await auth_client.get(path + "/guided", headers=_auth(host))).json()["state"]
    assert replay["proposal"]["text"] == "Ask a passer-by for help"
