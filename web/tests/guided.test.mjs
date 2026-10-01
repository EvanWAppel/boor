import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isGuidedPayload, CHECK_SCENES } from '../src/lib/guided.ts';

test('isGuidedPayload recognises every guided version, including v5', () => {
  for (const v of [1, 2, 3, 4, 5]) {
    assert.equal(isGuidedPayload({ type: `guided_cart_v${v}` }), true);
  }
  assert.equal(isGuidedPayload({ type: 'chat' }), false);
  assert.equal(isGuidedPayload({}), false);
  assert.equal(isGuidedPayload({ type: 42 }), false);
});

test('the v5 check scenes drive the approach UI and exclude story/battle scenes', () => {
  assert.ok(CHECK_SCENES.has('cart') && CHECK_SCENES.has('gate') && CHECK_SCENES.has('landing'));
  for (const scene of ['mara', 'battle', 'recap']) {
    assert.equal(CHECK_SCENES.has(scene), false);
  }
});

test('pauseControls: any seated person pauses live v5 play; only the pauser or host resumes', async () => {
  const { pauseControls } = await import('../src/lib/guided.ts');
  const base = { version: 5, scene: 'cart', phase: 'ready', seats: { a: {}, b: {} }, paused: null };
  assert.deepEqual(pauseControls(base, 'a', false), { canPause: true, canResume: false, canNote: false });
  // Not seated, lobby, or finished: no pause.
  assert.equal(pauseControls(base, 'z', false).canPause, false);
  assert.equal(pauseControls({ ...base, scene: null, phase: 'lobby' }, 'a', true).canPause, false);
  assert.equal(pauseControls({ ...base, phase: 'complete' }, 'a', true).canPause, false);
  assert.equal(pauseControls({ ...base, version: 4 }, 'a', true).canPause, false);
  const paused = { ...base, paused: { user_id: 'a', name: 'Ann', note: null } };
  assert.deepEqual(pauseControls(paused, 'a', false), { canPause: false, canResume: true, canNote: true });
  assert.deepEqual(pauseControls(paused, 'b', false), { canPause: false, canResume: false, canNote: false });
  assert.deepEqual(pauseControls(paused, 'b', true), { canPause: false, canResume: true, canNote: false });
});
