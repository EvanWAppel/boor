import assert from 'node:assert/strict';
import { test } from 'node:test';
import { maintainRoom } from '../src/lib/roomConnection.ts';

const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
function setup(t, overrides = {}) {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'] });
  const connections = [], statuses = [], sent = [];
  let tokenCount = 0, recoverCount = 0;
  const control = maintainRoom({
    baseUrl: 'https://example.test', sessionId: 'session',
    getToken: async () => `token-${++tokenCount}`,
    recover: async () => { recoverCount++; },
    onStatus: (...s) => statuses.push(s), onMessage: () => {},
    connect(options) {
      const connection = { options, closed: false };
      connections.push(connection);
      return { socket: { readyState: 1 }, send: m => sent.push(m),
        close() { connection.closed = true; options.onClose({ code: 1000 }); } };
    },
    ...overrides,
  });
  t.after(() => control.close());
  return { control, connections, statuses, sent, recoverCount: () => recoverCount };
}

test('refreshes the token and replays history after connection loss', async t => {
  const r = setup(t);
  await flush();
  r.connections[0].options.onOpen();
  r.connections[0].options.onMessage({ type: "ready" });
  await flush();
  assert.deepEqual(r.statuses.at(-1), ['open', null]);
  r.connections[0].options.onClose({ code: 1006 });
  assert.deepEqual(r.statuses.at(-1), ['reconnecting', null]);
  t.mock.timers.tick(1000);
  await flush();
  assert.equal(r.connections[1].options.token, 'token-2');
  r.connections[1].options.onOpen();
  r.connections[1].options.onMessage({ type: "ready" });
  await flush();
  assert.equal(r.recoverCount(), 2);
});

test('does not reconnect after permission rejection or disposal', async t => {
  const r = setup(t);
  await flush();
  r.connections[0].options.onClose({ code: 4403 });
  t.mock.timers.tick(60000);
  await flush();
  assert.equal(r.connections.length, 1);
  assert.deepEqual(r.statuses.at(-1), ['closed', 4403]);
  r.control.close();
  assert.equal(r.control.send({ type: 'chat', body: 'lost' }), false);
});

test('cancels a pending retry on unmount and ignores late callbacks', async t => {
  const r = setup(t);
  await flush();
  r.connections[0].options.onError();
  r.control.close();
  r.connections[0].options.onOpen();
  r.connections[0].options.onMessage({ type: "ready" });
  t.mock.timers.tick(60000);
  await flush();
  assert.equal(r.connections.length, 1);
  assert.equal(r.recoverCount(), 0);
});

test('heartbeats detect a silently dead socket', async t => {
  const r = setup(t);
  await flush();
  r.connections[0].options.onOpen();
  r.connections[0].options.onMessage({ type: "ready" });
  await flush();
  t.mock.timers.tick(15000);
  assert.deepEqual(r.sent, [{ type: 'ping' }]);
  t.mock.timers.tick(45001);
  assert.equal(r.connections[0].closed, true);
  t.mock.timers.tick(1000);
  await flush();
  assert.equal(r.connections.length, 2);
});

test('a failed replay retries instead of claiming the table is up to date', async t => {
  const r = setup(t, { recover: async () => { throw new Error('offline'); } });
  await flush();
  r.connections[0].options.onOpen();
  r.connections[0].options.onMessage({ type: "ready" });
  await flush();
  assert.deepEqual(r.statuses.at(-1), ['reconnecting', null]);
  assert.equal(r.connections[0].closed, true);
});
