import type { Portfolio } from "./types";

export class AuthError extends Error {}
export class ConnectionError extends Error {}

function requestTimeout(path: string) {
  if (path === "/refresh") return 180000;
  if (path === "/news/refresh" || path.startsWith("/ai/")) return 90000;
  if (path.startsWith("/search")) return 25000;
  return 15000;
}

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  options: { timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    options.timeoutMs ?? requestTimeout(path),
  );
  const cancel = () => controller.abort();
  options.signal?.addEventListener("abort", cancel, { once: true });
  if (options.signal?.aborted) controller.abort();
  try {
    const response = await fetch("/api" + path, {
      method,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(sessionStorage.getItem("token")
          ? { Authorization: "Bearer " + sessionStorage.getItem("token") }
          : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent("auth-required"));
      throw new AuthError("请输入访问口令");
    }
    if (!response.ok) {
      const fallback =
        response.status >= 500
          ? `服务暂时异常（HTTP ${response.status}），请稍后重试或检查后端日志`
          : `请求失败（HTTP ${response.status}）`;
      const error = await response.json().catch(() => ({ detail: fallback }));
      throw new Error(
        Array.isArray(error.detail)
          ? error.detail.map((x: { msg: string; type?: string }) => x.type === "extra_forbidden"
              ? "提交包含不支持的字段，请刷新页面后重试" : x.msg).join("；")
          : typeof error.detail === "string"
            ? error.detail
            : fallback,
      );
    }
    const result = await response.json();
    window.dispatchEvent(new CustomEvent("backend-connected"));
    return result;
  } catch (error) {
    if (options.signal?.aborted) throw error;
    if (controller.signal.aborted || error instanceof TypeError) {
      const message = controller.signal.aborted
        ? "请求超时，服务未在规定时间内响应。请稍后重试；提交过的操作请先核对结果。"
        : "无法连接后端服务，请确认本地服务已启动，再点击重试。";
      window.dispatchEvent(
        new CustomEvent("backend-unavailable", { detail: message }),
      );
      throw new ConnectionError(message);
    }
    if (error instanceof SyntaxError)
      throw new Error("接口返回了无效数据，请检查后端服务后重试");
    throw error;
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener("abort", cancel);
  }
}

export function savePortfolio(p: Portfolio): Promise<Portfolio> {
  // Response metadata and calculator/UI fields are never part of this contract.
  return api<Portfolio>("/portfolio", "PUT", {
    revision: p.revision,
    positions: p.positions.map(({ watch_id, shares, target, cap }) => ({ watch_id, shares, target, cap })),
    cash: p.cash,
    min_cash: p.min_cash,
    max_step: p.max_step,
    risk: p.risk,
    horizon: p.horizon,
  });
}
