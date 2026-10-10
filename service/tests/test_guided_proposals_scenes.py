"""v5 'try something else' beyond check scenes: the Mara conversation and the fight.

Conversation: an idea maps only to one of Mara's authored questions not yet asked
(the destination stays an explicit choice). Fight: only the character whose turn it
is may propose; it maps to Strike (with a target), Dodge, or Withdraw, or is
declined and the turn stays with them. The AI guide judges both under the same
rules as check scenes. Decided by Evan 2026-10-10.
"""

from boor_service import guided_scenes
from boor_service.ai.adjudicator import Adjudication
from tests.test_guided import command
from tests.test_guided_adventure import _me, _to_battle, begin, fixed_check, patch_combat
from tests.test_guided_ai import last_guide_event, latest
from tests.test_session_api import _auth


async def post(client, path, token, action, rev, **extra):
    return await client.post(
        path + "/guided", headers=_auth(token), json=command(action, rev, **extra)
    )


async def _to_mara(client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(client, mint_token)
    for token, action, extra in [
        (player, "approach", {"approach": "lift"}),
        (player, "roll", {}),
        (host, "continue", {}),
    ]:
        state = await act(token, action, state["revision"], **extra)
    assert state["scene"] == "mara" and state["phase"] == "conversation"
    return path, host, player, state, act


# --- Conversation ------------------------------------------------------------


async def test_conversation_proposal_becomes_an_unasked_question(
    auth_client, mint_token, monkeypatch
):
    path, host, player, state, act = await _to_mara(auth_client, mint_token, monkeypatch)
    proposed = await act(player, "propose", state["revision"], text="Who's been robbing carts?")
    assert proposed["proposal"]["text"] == "Who's been robbing carts?"
    # While it is open, the party can't ask or choose around it.
    rev = proposed["revision"]
    assert (await post(auth_client, path, player, "ask", rev, topic="road")).status_code == 409
    assert (await post(auth_client, path, player, "choose", rev, choice="town")).status_code == 409
    # The destination is never a valid mapping, only an unasked question.
    assert (
        await post(auth_client, path, host, "accept_proposal", rev, approach="town")
    ).status_code == 422
    accepted = await act(host, "accept_proposal", rev, approach="river")
    assert accepted["proposal"] is None and accepted["phase"] == "conversation"
    answer = accepted["conversation"]["answers"][-1]
    assert answer["topic"] == "river"
    assert answer["user_id"] == await _me(auth_client, player)
    # The idea's text stays in the log alongside Mara's answer.
    log = (await auth_client.get(path + "/log", headers=_auth(host))).json()
    assert "Who's been robbing carts?" in log[-1]["body"]


async def test_conversation_proposal_cannot_reask_and_decline_reopens(
    auth_client, mint_token, monkeypatch
):
    path, host, player, state, act = await _to_mara(auth_client, mint_token, monkeypatch)
    state = await act(player, "ask", state["revision"], topic="road")
    proposed = await act(player, "propose", state["revision"], text="Tell me about Emberlow again")
    assert (
        await post(
            auth_client, path, host, "accept_proposal", proposed["revision"], approach="road"
        )
    ).status_code == 422
    declined = await act(
        host, "decline_proposal", proposed["revision"], text="She already told you; ask another."
    )
    assert declined["proposal"] is None
    asked = await act(player, "ask", declined["revision"], topic="mara")
    assert len(asked["conversation"]["answers"]) == 2


async def test_no_conversation_proposal_once_every_question_is_asked(
    auth_client, mint_token, monkeypatch
):
    path, _host, player, state, act = await _to_mara(auth_client, mint_token, monkeypatch)
    for topic in ("road", "river", "mara"):
        state = await act(player, "ask", state["revision"], topic=topic)
    assert (
        await post(auth_client, path, player, "propose", state["revision"], text="One more thing")
    ).status_code == 409


# --- Fight -------------------------------------------------------------------


async def test_fight_proposal_on_your_turn_becomes_a_targeted_strike(
    auth_client, mint_token, monkeypatch
):
    path, host, player, state, act = await _to_battle(auth_client, mint_token, monkeypatch)
    # The watching host is not fighting, so cannot propose.
    assert (
        await post(auth_client, path, host, "propose", state["revision"], text="Charge!")
    ).status_code == 409
    proposed = await act(player, "propose", state["revision"], text="Shield-bash the bruiser")
    rev = proposed["revision"]
    # The turn waits on the proposal: no normal action around it.
    assert (
        await post(auth_client, path, player, "combat_action", rev, move="dodge")
    ).status_code == 409
    for bad in ("strike", "strike:nobody", "fly"):
        assert (
            await post(auth_client, path, host, "accept_proposal", rev, approach=bad)
        ).status_code == 422
    accepted = await act(host, "accept_proposal", rev, approach="strike:tough2")
    assert accepted["proposal"] is None
    assert accepted["encounter"]["fighters"]["tough2"]["hp"] == 0
    assert accepted["encounter"]["fighters"]["tough1"]["hp"] > 0


async def test_declined_fight_proposal_keeps_the_turn(auth_client, mint_token, monkeypatch):
    path, host, player, state, act = await _to_battle(auth_client, mint_token, monkeypatch)
    me = await _me(auth_client, player)
    proposed = await act(player, "propose", state["revision"], text="Summon a dragon")
    declined = await act(
        host, "decline_proposal", proposed["revision"], text="No dragons; try Strike or Dodge."
    )
    assert declined["proposal"] is None
    log = (await auth_client.get(path + "/log", headers=_auth(host))).json()
    assert "still" in log[-1]["body"] and "turn" in log[-1]["body"]
    encounter = declined["encounter"]
    assert encounter["order"][encounter["index"]] == me
    await act(player, "combat_action", declined["revision"], move="dodge")
    log = (await auth_client.get(path + "/log", headers=_auth(host))).json()
    assert "dodges" in log[-1]["body"]


async def test_stopping_the_fight_closes_an_open_proposal_visibly(
    auth_client, mint_token, monkeypatch
):
    path, host, player, state, act = await _to_battle(auth_client, mint_token, monkeypatch)
    proposed = await act(player, "propose", state["revision"], text="Throw sand in their eyes")
    stopped = await act(host, "stop_practice", proposed["revision"])
    assert stopped["phase"] == "combat_outcome" and stopped["proposal"] is None
    log = (await auth_client.get(path + "/log", headers=_auth(host))).json()
    assert "Throw sand in their eyes" in log[-1]["body"]


# --- AI guide ----------------------------------------------------------------


async def test_ai_guide_maps_a_conversation_idea_to_a_question(
    auth_client, mint_token, monkeypatch, fake_adjudicator
):
    fake_adjudicator.result = Adjudication(approach="mara", reason="That's about her cargo.")
    path, host, player, state, act = await _to_mara(auth_client, mint_token, monkeypatch)
    state = await act(player, "ask", state["revision"], topic="road")
    await act(player, "propose", state["revision"], text="What's in the crates?")
    ctx = fake_adjudicator.calls[0]
    assert [o["id"] for o in ctx.approaches] == ["river", "mara"]
    resolved = await latest(auth_client, path, host)
    assert resolved["proposal"] is None
    assert resolved["conversation"]["answers"][-1]["topic"] == "mara"
    event = await last_guide_event(auth_client, path, host)
    assert event["actor_label"] == "AI guide" and "her cargo" in event["body"]


async def test_ai_guide_maps_a_fight_idea_to_a_move(
    auth_client, mint_token, monkeypatch, fake_adjudicator
):
    patch_combat(monkeypatch)
    fake_adjudicator.result = Adjudication(approach="dodge", reason="Ducking low is a dodge.")
    path, host, player, state, act = await _to_battle(auth_client, mint_token, monkeypatch)
    await act(player, "propose", state["revision"], text="I duck behind the cart")
    ctx = fake_adjudicator.calls[0]
    assert [o["id"] for o in ctx.approaches] == [
        "strike:tough1",
        "strike:tough2",
        "dodge",
        "withdraw",
    ]
    resolved = await latest(auth_client, path, host)
    assert resolved["proposal"] is None
    event = await last_guide_event(auth_client, path, host)
    body = event["body"]
    assert "as Dodge" in body and "dodges" in body
    # The guide's reason reads right after the mapping, before the turn plays out.
    assert body.index("Ducking low is a dodge.") < body.index("dodges")
