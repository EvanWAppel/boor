import assert from 'node:assert/strict';
import { test } from 'node:test';
import { recapsToReadFirst, recapStatusLabel } from '../src/lib/recaps.ts';

// AI-09: a player's finished, unread recaps are shown before they sit down at the
// table (decided 2026-10-10). Others' shared recaps and pending/failed ones never block.
test('only my finished, unread recaps gate the table', () => {
  const base = { status: 'ready', mine: true, read: false, shared: false };
  const recaps = [
    { ...base, id: 'a' },
    { ...base, id: 'b', read: true },
    { ...base, id: 'c', mine: false, shared: true },
    { ...base, id: 'd', status: 'pending' },
    { ...base, id: 'e', status: 'failed' },
  ];
  assert.deepEqual(recapsToReadFirst(recaps).map(r => r.id), ['a']);
  assert.deepEqual(recapsToReadFirst([]), []);
});

test('status labels explain pending and failed recaps', () => {
  assert.match(recapStatusLabel({ status: 'pending' }, false), /being written/i);
  assert.match(recapStatusLabel({ status: 'failed' }, true), /retry/i);
  assert.doesNotMatch(recapStatusLabel({ status: 'failed' }, false), /retry/i);
  assert.equal(recapStatusLabel({ status: 'ready' }, false), '');
});
