import type { Portfolio } from "./types";

function hundredths(value: number | string): number | null {
  const text = String(value).trim();
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text)) return null;
  if ((text.split(".")[1] || "").replace(/0+$/, "").length > 2) return null;
  const number = Number(text);
  return Number.isFinite(number) && number >= 0 && number <= 100 ? Math.round(number * 100) : null;
}

export function portfolioIssue(p: Portfolio): string {
  const cash = hundredths(p.cash), minimum = hundredths(p.min_cash), step = hundredths(p.max_step);
  if (cash === null) return "现金份额须为 0～100，最多两位小数";
  if (minimum === null) return "最低现金须为 0～100，最多两位小数";
  if (step === null || step === 0 || step > 500) return "单次调整上限须大于 0 且不超过 5 份，最多两位小数";
  const ids = new Set<string>();
  let total = cash;
  for (const [index, position] of p.positions.entries()) {
    const shares = hundredths(position.shares), cap = hundredths(position.cap);
    if (shares === null || cap === null || (position.target !== null && hundredths(position.target) === null))
      return `第 ${index + 1} 项持仓的份额、目标及上限须为 0～100，最多两位小数`;
    if (shares > cap) return `第 ${index + 1} 项当前份额超过仓位上限，请提高上限或调整份额`;
    if (ids.has(position.watch_id)) return "不能重复配置同一标的";
    ids.add(position.watch_id);
    total += shares;
  }
  return total === 10000 ? "" : `持仓和现金必须合计 100 份，当前差额 ${(10000 - total) / 100} 份`;
}
