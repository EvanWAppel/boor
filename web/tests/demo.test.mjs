import assert from 'node:assert/strict';
import { test } from 'node:test';
import { GUEST_KEY, guestToken, isDemoHost, requestHost } from '../src/lib/demo.ts';

test('the public demo hostname is a demo host; the real one is not', () => {
  assert.equal(isDemoHost('boor-demo.evanappel.me', {}), true);
  assert.equal(isDemoHost('BOOR-DEMO.evanappel.me:443', {}), true);
  assert.equal(isDemoHost('web-production-0e6881.up.railway.app', {}), false);
  assert.equal(isDemoHost(null, {}), false);
});

test('DEMO_HOSTNAMES replaces the default list', () => {
  const env = { DEMO_HOSTNAMES: 'demo.localhost, other.test' };
  assert.equal(isDemoHost('demo.localhost:3000', env), true);
  assert.equal(isDemoHost('boor-demo.evanappel.me', env), false);
});

test('the local switch is off by default and makes every host a demo host', () => {
  assert.equal(isDemoHost('localhost:3000', {}), false);
  assert.equal(isDemoHost('localhost:3000', { BOOR_DEMO: '0' }), false);
  assert.equal(isDemoHost('localhost:3000', { BOOR_DEMO: '1' }), true);
  assert.equal(isDemoHost(null, { BOOR_DEMO: '1' }), true);
});

test('the request host prefers the forwarded host from the edge', () => {
  const headers = new Headers({ host: 'internal:8080', 'x-forwarded-host': 'boor-demo.evanappel.me' });
  assert.equal(requestHost(headers), 'boor-demo.evanappel.me');
  assert.equal(requestHost(new Headers({ host: 'a.test' })), 'a.test');
});

function memoryStorage() {
  const items = new Map();
  return {
    getItem: (k) => items.get(k) ?? null,
    setItem: (k, v) => items.set(k, v),
    items,
  };
}

test('a browser gets one stable guest token, shaped for the service', () => {
  const storage = memoryStorage();
  const first = guestToken(storage, () => 'a'.repeat(32));
  assert.equal(first, `demo.${'a'.repeat(32)}`);
  assert.equal(storage.items.get(GUEST_KEY), 'a'.repeat(32));
  assert.equal(guestToken(storage, () => 'b'.repeat(32)), first);
});

test('a corrupted stored guest id is replaced', () => {
  const storage = memoryStorage();
  storage.setItem(GUEST_KEY, 'not-hex');
  assert.equal(guestToken(storage, () => 'c'.repeat(32)), `demo.${'c'.repeat(32)}`);
});
