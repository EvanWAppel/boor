import assert from 'node:assert/strict';
import { test } from 'node:test';
import { connectSessionRoom } from '../src/lib/ws.ts';

// SEC-01: the Clerk token travels as a WS subprotocol, never in the URL, so it
// can't end up in the service's access log.
test('sends the token as a bearer subprotocol, not in the URL', (t) => {
  const opened = [];
  class FakeWebSocket { constructor(url, protocols) { opened.push({ url, protocols }); } send() {} close() {} }
  const original = globalThis.WebSocket;
  globalThis.WebSocket = FakeWebSocket;
  t.after(() => { globalThis.WebSocket = original; });

  connectSessionRoom({ baseUrl: 'https://svc.test', sessionId: 's1', token: 'eyJ.secret.sig', onMessage: () => {} });

  assert.equal(opened.length, 1);
  assert.equal(opened[0].url, 'wss://svc.test/ws/sessions/s1');
  assert.deepEqual(opened[0].protocols, ['bearer', 'eyJ.secret.sig']);
});
