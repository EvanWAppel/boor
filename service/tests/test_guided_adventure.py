"""Version-five data-driven adventure: full paths, branch checks, combat, recap.

The shared infra (lock, idempotency, revision, ended-session) is exercised by the
v1-v4 suites; these tests focus on the v5 scene graph and its transitions.
"""

from types import SimpleNamespace

from boor_service import guided_combat, guided_scenes
from boor_service.mechanics import ability_check as real_ability_check
from tests.test_guided import command, setup
from tests.test_session_api import _auth


def fixed_check(die):
    class Fixed:
        def randint(self, a, b):
            assert a <= die <= b
            return die

    return lambda bonus, dc: real_ability_check(bonus, dc=dc, rng=Fixed())


def patch_combat(monkeypatch):
    """Player rolls first, one-shots any enemy, and the enemies always miss."""

    def fake_roll_d20(bonus=0, **_kwargs):
        return SimpleNamespace(total=10 + bonus)

    def fake_attack_roll(bonus, _ac, **_kwargs):
        hit = bonus >= 5  # players (mod + proficiency) hit; enemies (+3) miss
        roll = SimpleNamespace(dice=(20 if hit else 2,), dropped=())
        return SimpleNamespace(is_hit=hit, is_critical=hit, total=roll.dice[0] + bonus, roll=roll)

    def fake_roll_damage(_notation, **_kwargs):
        return SimpleNamespace(total=100)

    monkeypatch.setattr(guided_combat, "roll_d20", fake_roll_d20)
    monkeypatch.setattr(guided_combat, "attack_roll", fake_attack_roll)
    monkeypatch.setattr(guided_combat, "roll_damage", fake_roll_damage)


async def _me(client, token):
    return (await client.get("/me", headers=_auth(token))).json()["id"]


async def begin(client, mint_token):
    """Start a v5 run: player plays the guardian, host watches, adventure begins at the cart."""
    path, host, player = await setup(client, mint_token)

    async def act(token, action, rev, **extra):
        r = await client.post(
            path + "/guided", headers=_auth(token), json=command(action, rev, **extra)
        )
        assert r.status_code == 200, r.text
        return r.json()["state"]

    state = await act(host, "start", 0)
    assert state["version"] == 5
    state = await act(player, "select", state["revision"], pregen="guardian")
    state = await act(player, "ready", state["revision"])
    state = await act(host, "watch", state["revision"])
    state = await act(host, "begin", state["revision"])
    assert state["scene"] == "cart" and state["phase"] == "ready"
    return path, host, player, state, act


async def test_town_path_success_reaches_recap_and_complete(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    patch_combat(monkeypatch)
    path, host, player, state, act = await begin(auth_client, mint_token)
    player_id = await _me(auth_client, player)

    # Cart check (Athletics), then continue to Mara.
    state = await act(player, "approach", state["revision"], approach="lift")
    assert state["scene"] == "cart" and state["pending"]["skill"] == "athletics"
    state = await act(player, "roll", state["revision"])
    assert state["result"]["success"] is True
    state = await act(host, "continue", state["revision"])
    assert state["scene"] == "mara" and state["phase"] == "conversation"

    # Conversation: ask, then choose the town branch.
    state = await act(player, "ask", state["revision"], topic="road")
    state = await act(player, "choose", state["revision"], choice="town")
    assert state["phase"] == "decision"
    state = await act(host, "continue", state["revision"])
    assert state["scene"] == "gate"
    assert [a["skill"] for a in state["actions"]] == ["persuasion", "insight"]

    # Second, different check (Persuasion).
    state = await act(player, "approach", state["revision"], approach="vouch")
    assert state["pending"]["skill"] == "persuasion"
    state = await act(player, "roll", state["revision"])
    state = await act(host, "continue", state["revision"])
    assert state["scene"] == "battle" and state["phase"] == "combat"
    assert set(k for k, f in state["encounter"]["fighters"].items() if f["user_id"] is None) == {
        "tough1",
        "tough2",
    }

    # Fight: one-shot both enemies to victory.
    for _ in range(4):
        if state["phase"] != "combat":
            break
        fighters = state["encounter"]["fighters"]
        targets = [
            k
            for k in state["encounter"]["order"]
            if fighters[k]["user_id"] is None and fighters[k]["hp"] > 0
        ]
        state = await act(
            player, "combat_action", state["revision"], move="strike", target=targets[0]
        )
    assert state["phase"] == "combat_outcome"
    assert state["encounter"]["outcome"]["reason"] == "victory"

    state = await act(host, "continue", state["revision"])
    assert state["scene"] == "recap" and state["phase"] == "recap"
    assert any("token" in line for line in state["recap"]["lines"])
    assert "Emberlow" in state["recap"]["next"]
    state = await act(host, "continue", state["revision"])
    assert state["phase"] == "complete"
    assert player_id in state["participants"]
    # A finished introduction has no live play to pause.
    r = await auth_client.post(
        path + "/guided", headers=_auth(host), json=command("pause", state["revision"])
    )
    assert r.status_code == 409


async def test_river_path_failure_continues_and_withdraw(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(1))  # every check fails
    patch_combat(monkeypatch)
    _path, host, player, state, act = await begin(auth_client, mint_token)

    state = await act(player, "approach", state["revision"], approach="lift")
    state = await act(player, "roll", state["revision"])
    assert state["result"]["success"] is False
    state = await act(host, "continue", state["revision"])
    state = await act(player, "ask", state["revision"], topic="river")
    state = await act(player, "choose", state["revision"], choice="river")
    state = await act(host, "continue", state["revision"])
    assert state["scene"] == "landing"
    assert [a["skill"] for a in state["actions"]] == ["perception", "stealth"]

    state = await act(player, "approach", state["revision"], approach="scout")
    state = await act(player, "roll", state["revision"])
    assert state["result"]["success"] is False
    # A failed check must not dead-end: it still advances into the fight.
    state = await act(host, "continue", state["revision"])
    assert state["scene"] == "battle" and state["phase"] == "combat"
    # Failure means the enemies are the tougher (un-softened) version.
    assert state["encounter"]["fighters"]["bandit1"]["max_hp"] == 8

    state = await act(player, "combat_action", state["revision"], move="withdraw")
    assert state["phase"] == "combat_outcome"
    assert state["encounter"]["outcome"]["reason"] == "withdrawn"
    state = await act(host, "continue", state["revision"])
    state = await act(host, "continue", state["revision"])
    assert state["phase"] == "complete"


async def _to_battle(client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    patch_combat(monkeypatch)
    path, host, player, state, act = await begin(client, mint_token)
    for token, action, extra in [
        (player, "approach", {"approach": "lift"}),
        (player, "roll", {}),
        (host, "continue", {}),
        (player, "ask", {"topic": "road"}),
        (player, "choose", {"choice": "town"}),
        (host, "continue", {}),
        (player, "approach", {"approach": "vouch"}),
        (player, "roll", {}),
        (host, "continue", {}),
    ]:
        state = await act(token, action, state["revision"], **extra)
    assert state["scene"] == "battle" and state["phase"] == "combat"
    return path, host, player, state, act


async def test_combat_target_and_turn_rules(auth_client, mint_token, monkeypatch):
    path, host, player, state, _act = await _to_battle(auth_client, mint_token, monkeypatch)
    rev = state["revision"]

    async def post(token, **extra):
        return await auth_client.post(
            path + "/guided", headers=_auth(token), json=command("combat_action", rev, **extra)
        )

    # Two live enemies -> a target is required, and it must be a real enemy.
    assert (await post(player, move="strike")).status_code == 409
    assert (await post(player, move="strike", target="nope")).status_code == 409
    # The watching host is not in the fight and it is not their turn.
    assert (await post(host, move="strike", target="tough1")).status_code == 403
    ok = await post(player, move="strike", target="tough1")
    assert ok.status_code == 200
    assert ok.json()["state"]["encounter"]["fighters"]["tough1"]["hp"] == 0


async def test_spectator_cannot_take_scene_actions(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, _player, state, _act = await begin(auth_client, mint_token)
    # The host chose to watch, so they hold no character and cannot drive a scene.
    r = await auth_client.post(
        path + "/guided",
        headers=_auth(host),
        json=command("approach", state["revision"], approach="lift"),
    )
    assert r.status_code == 409


async def test_resolved_roll_replays_and_retries_once(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    state = await act(player, "approach", state["revision"], approach="lift")
    roll = command("roll", state["revision"])
    first = await auth_client.post(path + "/guided", headers=_auth(player), json=roll)
    assert first.status_code == 200
    # Same request id -> same committed result, no second roll.
    retry = await auth_client.post(path + "/guided", headers=_auth(player), json=roll)
    assert retry.json()["state"]["result"] == first.json()["state"]["result"]
    # A fresh GET recovers the same resolved state.
    replay = (await auth_client.get(path + "/guided", headers=_auth(host))).json()["state"]
    assert replay["result"] == first.json()["state"]["result"]
    assert replay["phase"] == "outcome"


async def test_ended_session_rejects_scene_commands(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, _act = await begin(auth_client, mint_token)
    assert (await auth_client.post(path + "/end", headers=_auth(host))).status_code == 200
    r = await auth_client.post(
        path + "/guided",
        headers=_auth(player),
        json=command("approach", state["revision"], approach="lift"),
    )
    assert r.status_code == 409
