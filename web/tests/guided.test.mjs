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

// "Try something else" beyond check scenes (decided 2026-10-10). Option ids must
// match boor_service.guided_scenes.proposal_options exactly.
test('proposalOptions: approaches, unasked questions, or moves for the active fighter', async () => {
  const { proposalOptions } = await import('../src/lib/guided.ts');
  const actions = [{ id: 'lift', label: 'Lift', skill: 'athletics', hint: 'h' }];
  assert.deepEqual(proposalOptions({ scene: 'cart', actions }).map(o => o.id), ['lift']);

  const conversation = { questions: [{ id: 'road', label: 'Road?' }, { id: 'river', label: 'River?' }, { id: 'mara', label: 'You?' }],
    answers: [{ topic: 'road' }] };
  assert.deepEqual(proposalOptions({ scene: 'mara', conversation }).map(o => o.id), ['river', 'mara']);

  const f = (name, user_id, hp = 5, withdrawn = false) => ({ name, user_id, hp, withdrawn });
  const encounter = { order: ['p1', 'b1', 'b2', 'b3'], index: 0, outcome: null,
    fighters: { p1: f('Rowan', 'p1'), b1: f('Bandit', null), b2: f('Down', null, 0), b3: f('Cloak', null) } };
  assert.deepEqual(proposalOptions({ scene: 'battle', encounter }).map(o => o.id),
    ['strike:b1', 'strike:b3', 'dodge', 'withdraw']);
  assert.deepEqual(proposalOptions({ scene: 'recap' }), []);
});

test('canPropose: playing characters in open check/conversation steps; only the active fighter', async () => {
  const { canPropose } = await import('../src/lib/guided.ts');
  const participants = { a: {}, b: {} };
  const base = { version: 5, participants, proposal: null };
  assert.equal(canPropose({ ...base, scene: 'cart', phase: 'ready', actions: [{ id: 'lift' }] }, 'a'), true);
  assert.equal(canPropose({ ...base, scene: 'cart', phase: 'check', actions: [{ id: 'lift' }] }, 'a'), false);
  assert.equal(canPropose({ ...base, scene: 'cart', phase: 'ready', actions: [{ id: 'lift' }] }, 'watcher'), false);
  const conversation = { questions: [{ id: 'road' }], answers: [] };
  assert.equal(canPropose({ ...base, scene: 'mara', phase: 'conversation', conversation }, 'a'), true);
  assert.equal(canPropose({ ...base, scene: 'mara', phase: 'conversation', conversation: { ...conversation, answers: [{ topic: 'road' }] } }, 'a'), false);
  const encounter = { order: ['a', 'b', 'x'], index: 0, outcome: null,
    fighters: { a: { user_id: 'a', hp: 5 }, b: { user_id: 'b', hp: 5 }, x: { user_id: null, hp: 5, name: 'X' } } };
  assert.equal(canPropose({ ...base, scene: 'battle', phase: 'combat', encounter }, 'a'), true);
  assert.equal(canPropose({ ...base, scene: 'battle', phase: 'combat', encounter }, 'b'), false);
  // One open proposal at a time, and v5 only.
  assert.equal(canPropose({ ...base, scene: 'battle', phase: 'combat', encounter, proposal: { user_id: 'a' } }, 'a'), false);
  assert.equal(canPropose({ ...base, version: 4, scene: 'cart', phase: 'ready', actions: [{ id: 'lift' }] }, 'a'), false);
});
