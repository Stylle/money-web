export class AuthError extends Error {}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
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
    const error = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(
      Array.isArray(error.detail)
        ? error.detail.map((x: { msg: string }) => x.msg).join("；")
        : error.detail || "请求失败",
    );
  }
  return response.json();
}
