import assert from "node:assert/strict";
import { test } from "node:test";
import "fake-indexeddb/auto";
import { flushOfflineQueue, resolveAuthMode, writeApi } from "../lib/api";
import { enqueue, readQueue, removeQueued } from "../lib/offline-queue";

test("production frontend builds always use Supabase Auth", () => {
  assert.equal(resolveAuthMode("demo", "production"), "supabase");
  assert.equal(resolveAuthMode("demo", "development"), "demo");
  assert.equal(resolveAuthMode("supabase", "development"), "supabase");
});

test("offline record is saved locally and replayed after reconnect", async () => {
  const windowEvents = new EventTarget();
  Object.defineProperty(globalThis, "window", { configurable: true, value: windowEvents });
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { onLine: false } });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => { throw new TypeError("network unavailable"); }) as typeof fetch;

  const body = { event_type: "clinical_observation", summary: "offline note" };
  const saved = await writeApi("/api/v1/animals/demo/health-events", "demo-token", body);
  assert.deepEqual(saved, { queuedOffline: true });
  const queued = await readQueue();
  assert.equal(queued.length, 1);
  assert.deepEqual(JSON.parse(queued[0].body), body);

  const requests: Array<{ url: string; method: string | undefined; idempotencyKey: string | null }> = [];
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { onLine: true } });
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    requests.push({ url: String(input), method: init?.method, idempotencyKey: new Headers(init?.headers).get("Idempotency-Key") });
    return new Response("{}", { status: 201, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;

  const result = await flushOfflineQueue("demo-token");
  assert.deepEqual(result, { synced: 1, pending: 0 });
  assert.equal(requests[0].method, "POST");
  assert.equal(requests[0].url, "http://localhost:8000/api/v1/animals/demo/health-events");
  assert.ok(requests[0].idempotencyKey);
  assert.equal((await readQueue()).length, 0);

  globalThis.fetch = originalFetch;
  for (const item of await readQueue()) await removeQueued(item.id);
  delete (globalThis as { window?: unknown }).window;
  delete (globalThis as { navigator?: unknown }).navigator;
});

test("offline replay is scoped to the currently authenticated user", async () => {
  const windowEvents = new EventTarget();
  Object.defineProperty(globalThis, "window", { configurable: true, value: windowEvents });
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { onLine: true } });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: { getItem: (key: string) => key === "terravanta-account-id-v1" ? "farmer-a" : JSON.stringify({ user: { id: "farmer-a" } }) } });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response("{}", { status: 201, headers: { "Content-Type": "application/json" } })) as typeof fetch;

  await enqueue("/api/v1/farms", "POST", "{}", "farmer-a");
  await enqueue("/api/v1/farms", "POST", "{}", "farmer-b");
  const result = await flushOfflineQueue("farmer-token");
  assert.deepEqual(result, { synced: 1, pending: 0 });
  assert.equal((await readQueue("farmer-a")).length, 0);
  assert.equal((await readQueue("farmer-b")).length, 1);

  for (const item of await readQueue()) await removeQueued(item.id);
  globalThis.fetch = originalFetch;
  delete (globalThis as { window?: unknown }).window;
  delete (globalThis as { navigator?: unknown }).navigator;
  delete (globalThis as { localStorage?: unknown }).localStorage;
});
