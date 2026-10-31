import { test } from "node:test";
import assert from "node:assert/strict";
import { portfolioIssue } from "../src/portfolio.ts";

const snapshot = { revision: 0, positions: [{ watch_id: "US:QQQ", shares: "33.33", target: null, cap: 40 }],
  cash: "66.67", min_cash: 10, max_step: 1, risk: "balanced", horizon: "medium", updated_at: "test" };

test("decimal allocations use exact hundredths and permit zero optional positions", () => {
  assert.equal(portfolioIssue(snapshot), "");
  assert.equal(portfolioIssue({ ...snapshot, positions: [...snapshot.positions, { watch_id: "US:SPY", shares: 0, target: null, cap: "40.00" }] }), "");
});

test("a balanced sum alone does not permit blank, over-cap or over-precision fields", () => {
  assert.match(portfolioIssue({ ...snapshot, positions: [{ ...snapshot.positions[0], cap: 30 }] }), /超过仓位上限/);
  assert.match(portfolioIssue({ ...snapshot, cash: "66.671" }), /最多两位小数/);
  assert.match(portfolioIssue({ ...snapshot, max_step: "" }), /单次调整上限/);
  assert.match(portfolioIssue({ ...snapshot, max_step: "0" }), /单次调整上限/);
  assert.match(portfolioIssue({ ...snapshot, cash: "NaN" }), /现金份额/);
  assert.match(portfolioIssue({ ...snapshot, cash: 66 }), /合计 100/);
});
