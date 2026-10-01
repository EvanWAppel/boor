"""v5 pause/resume: any participant pauses instantly; the pauser or host resumes.

A pause freezes game actions only (chat is a separate endpoint). The optional note
is added after the pause has already taken effect.
"""

from boor_service import guided_scenes
from tests.test_guided import command
from tests.test_guided_adventure import begin, fixed_check
from tests.test_session_api import _auth


async def post(client, path, token, action, rev, **extra):
    return await client.post(
        path + "/guided", headers=_auth(token), json=command(action, rev, **extra)
    )


async def test_player_pauses_freezes_actions_then_resumes(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    me = (await auth_client.get("/me", headers=_auth(player))).json()["id"]

    paused = await act(player, "pause", state["revision"])
    assert paused["paused"] == {"user_id": me, "name": paused["paused"]["name"], "note": None}
    # The scene underneath is untouched.
    assert paused["scene"] == "cart" and paused["phase"] == "ready"
    # Game actions are frozen for everyone, including the host.
    assert (
        await post(auth_client, path, player, "approach", paused["revision"], approach="lift")
    ).status_code == 409
    assert (
        await post(auth_client, path, player, "propose", paused["revision"], text="anything")
    ).status_code == 409
    # Already paused.
    assert (await post(auth_client, path, host, "pause", paused["revision"])).status_code == 409

    # The note comes after the pause, and only from the pauser.
    assert (
        await post(auth_client, path, host, "pause_note", paused["revision"], text="not mine")
    ).status_code == 403
    assert (
        await post(auth_client, path, player, "pause_note", paused["revision"], text="  ")
    ).status_code == 422
    noted = await act(player, "pause_note", paused["revision"], text="Need a minute")
    assert noted["paused"]["note"] == "Need a minute"

    # The pause survives a refresh.
    replay = (await auth_client.get(path + "/guided", headers=_auth(host))).json()["state"]
    assert replay["paused"]["note"] == "Need a minute"

    resumed = await act(player, "resume", noted["revision"])
    assert resumed["paused"] is None
    approached = await act(player, "approach", resumed["revision"], approach="lift")
    assert approached["phase"] == "check"
    # Resuming when not paused is a conflict.
    stale = await post(auth_client, path, host, "resume", approached["revision"])
    assert stale.status_code == 409


async def test_host_can_resume_and_pause_holds_mid_check(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    state = await act(player, "approach", state["revision"], approach="lift")
    # The watching host can pause too; a pending roll is held, not discarded.
    paused = await act(host, "pause", state["revision"])
    assert paused["pending"]["skill"] == "athletics"
    assert (await post(auth_client, path, player, "roll", paused["revision"])).status_code == 409
    # Only the pauser (here the host) may add the note.
    assert (
        await post(auth_client, path, player, "pause_note", paused["revision"], text="hmm")
    ).status_code == 403
    resumed = await act(host, "resume", paused["revision"])
    rolled = await act(player, "roll", resumed["revision"])
    assert rolled["result"]["success"] is True


async def test_player_cannot_resume_someone_elses_pause(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    paused = await act(host, "pause", state["revision"])
    # A non-host who didn't pause cannot override the pause.
    assert (await post(auth_client, path, player, "resume", paused["revision"])).status_code == 403
    assert (await act(host, "resume", paused["revision"]))["paused"] is None


async def test_pause_is_unavailable_in_the_lobby(auth_client, mint_token):
    from tests.test_guided import setup

    path, host, _player = await setup(auth_client, mint_token)
    r = await post(auth_client, path, host, "start", 0)
    assert r.status_code == 200
    started = r.json()["state"]
    assert started["paused"] is None
    assert (await post(auth_client, path, host, "pause", started["revision"])).status_code == 409


async def test_pause_edge_cases(auth_client, mint_token, monkeypatch):
    monkeypatch.setattr(guided_scenes, "ability_check", fixed_check(20))
    path, host, player, state, act = await begin(auth_client, mint_token)
    # A note or resume with nothing paused is a conflict.
    assert (
        await post(auth_client, path, player, "pause_note", state["revision"], text="hi")
    ).status_code == 409
    # The host joined as a spectator here; spectators can pause too.
    paused = await act(host, "pause", state["revision"])
    assert paused["paused"]["note"] is None
    resumed = await act(host, "resume", paused["revision"])
    assert resumed["paused"] is None
