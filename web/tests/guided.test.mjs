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
