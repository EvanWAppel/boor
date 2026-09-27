import assert from 'node:assert/strict';
import { test } from 'node:test';
import { lobbyStatus } from '../src/lib/lobby.ts';

const screenshotState = () => ({
  participants: { player: { name: 'Wren' } },
  seats: {
    host: { player_name: 'Evan Appel', watching: true, ready: true },
    player: { player_name: 'Evil Evan', watching: false, ready: false },
  },
});

test('reported lobby tells the host who is blocking and the player what to click', () => {
  const state = screenshotState();
  assert.equal(lobbyStatus(state, 'host', true).canBegin, false);
  assert.match(lobbyStatus(state, 'host', true).message, /Waiting for Evil Evan/);
  assert.match(lobbyStatus(state, 'player', false).message, /chosen Wren.*I’m ready/);
  state.seats.player.ready = true;
  assert.equal(lobbyStatus(state, 'host', true).canBegin, true);
  assert.match(lobbyStatus(state, 'host', true).message, /Click “Begin adventure”/);
  assert.match(lobbyStatus(state, 'player', false).message, /host can now begin/);
});

test('all spectators are told that someone must play even if everyone is ready', () => {
  const state = screenshotState();
  state.participants = {};
  state.seats.player = { player_name: 'Evil Evan', watching: true, ready: true };
  for (const id of ['host', 'player']) {
    const status = lobbyStatus(state, id, id === 'host');
    assert.equal(status.canBegin, false);
    assert.match(status.message, /At least one person needs to play/);
  }
});

test('an unready spectator and an undecided player receive their own next step', () => {
  const state = screenshotState();
  state.seats.host.ready = false;
  assert.match(lobbyStatus(state, 'host', true).message, /ready to watch/);
  state.participants = { host: { name: 'Rowan' } };
  assert.match(lobbyStatus(state, 'player', false).message, /Choose a character/);
});
