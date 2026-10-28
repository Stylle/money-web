import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { api, AuthError, ConnectionError } from "../src/api.ts";

const originalFetch = globalThis.fetch;
let events;
beforeEach(() => {
  globalThis.window = new EventTarget();
  globalThis.sessionStorage = { getItem: () => null };
  events = [];
  for (const type of [
    "backend-connected",
    "backend-unavailable",
    "auth-required",
  ]) {
    window.addEventListener(type, (event) =>
      events.push({ type, detail: event.detail }),
    );
  }
});
afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("network failure explains that the backend must be started", async () => {
  globalThis.fetch = async () => {
    throw new TypeError("Failed to fetch");
  };
  await assert.rejects(
    api("/settings"),
    (error) =>
      error instanceof ConnectionError &&
      error.message.includes("无法连接后端服务"),
  );
  assert.equal(events[0].type, "backend-unavailable");
  assert.ok(!events[0].detail.includes("Failed to fetch"));
});

test("stalled requests time out and writes are never retried automatically", async () => {
  let calls = 0;
  globalThis.fetch = (_url, { signal }) => {
    calls++;
    return new Promise((_resolve, reject) =>
      signal.addEventListener("abort", () =>
        reject(new DOMException("Aborted", "AbortError")),
      ),
    );
  };
  await assert.rejects(
    api("/portfolio", "PUT", { revision: 1 }, { timeoutMs: 10 }),
    /请求超时/,
  );
  assert.equal(calls, 1);
  assert.equal(events[0].type, "backend-unavailable");
});

test("obsolete searches can be cancelled without announcing an outage", async () => {
  const controller = new AbortController();
  globalThis.fetch = (_url, { signal }) =>
    new Promise((_resolve, reject) =>
      signal.addEventListener("abort", () =>
        reject(new DOMException("Aborted", "AbortError")),
      ),
    );
  const pending = api("/search?market=US&q=old", "GET", undefined, {
    signal: controller.signal,
  });
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
  assert.deepEqual(events, []);
});

test("successful request preserves auth headers and announces recovery", async () => {
  sessionStorage.getItem = () => "test-session-token";
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/settings");
    assert.equal(options.headers.Authorization, "Bearer test-session-token");
    return new Response(JSON.stringify({ markets: ["US"] }));
  };
  assert.deepEqual(await api("/settings"), { markets: ["US"] });
  assert.equal(events[0].type, "backend-connected");
});

test("unauthorized response opens auth instead of reporting a network problem", async () => {
  globalThis.fetch = async () => new Response("{}", { status: 401 });
  await assert.rejects(api("/settings"), AuthError);
  assert.equal(events[0].type, "auth-required");
  assert.equal(events.length, 1);
});

test("HTML gateway errors still show their HTTP status", async () => {
  globalThis.fetch = async () =>
    new Response("<html>Bad Gateway</html>", { status: 502 });
  await assert.rejects(api("/settings"), /HTTP 502/);
});

test("malformed successful JSON does not leave callers waiting forever", async () => {
  globalThis.fetch = async () =>
    new Response("<html>not an API response</html>");
  await assert.rejects(api("/settings"), /接口返回了无效数据/);
});

test("validation errors stay readable", async () => {
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ detail: [{ msg: "份额必须合计 100" }] }), {
      status: 422,
    });
  await assert.rejects(api("/portfolio", "PUT", {}), /份额必须合计 100/);
});
