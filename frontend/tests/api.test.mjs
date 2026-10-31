import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { api, AuthError, ConnectionError, savePortfolio } from "../src/api.ts";

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

test("saving a GET portfolio snapshot sends editable fields only, including on repeat saves", async () => {
  const snapshot = { revision: 0, updated_at: "2026-10-31T00:00:00+00:00",
    positions: [{ watch_id: "US:QQQ", shares: "33.33", target: null, cap: 40, display: "not writable" }],
    cash: "66.67", min_cash: 10, max_step: 1, risk: "balanced", horizon: "medium",
    capital: 1000000, future_metadata: "read only" };
  let revision = 0;
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/portfolio");
    const body = JSON.parse(options.body);
    assert.deepEqual(Object.keys(body).sort(), ["revision", "positions", "cash", "min_cash", "max_step", "risk", "horizon"].sort());
    assert.deepEqual(Object.keys(body.positions[0]).sort(), ["watch_id", "shares", "target", "cap"].sort());
    assert.equal(body.revision, revision);
    assert.equal(body.cash, "66.67");
    assert.equal(body.positions[0].shares, "33.33");
    assert.ok(!options.body.includes("1000000"));
    return new Response(JSON.stringify({ ...snapshot, ...body, revision: ++revision }));
  };
  const saved = await savePortfolio(snapshot);
  assert.equal((await savePortfolio(saved)).revision, 2);
  assert.equal(snapshot.revision, 0);
});

test("unexpected form fields produce a Chinese refresh hint", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: [{ type: "extra_forbidden", msg: "Extra inputs are not permitted" }] }), { status: 422 });
  await assert.rejects(api("/portfolio", "PUT", {}), /提交包含不支持的字段，请刷新页面后重试/);
});
