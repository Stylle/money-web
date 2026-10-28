import { useEffect, useState } from "react";
import { ChevronRight, ExternalLink, RefreshCw } from "lucide-react";
import { api } from "./api";

type Health = {
  status?: string;
  last_attempt?: string;
  last_success?: string;
  last_error?: string;
  items?: number;
  retry_after?: string;
};
type SourceData = {
  news: {
    id: string;
    name: string;
    url: string;
    kind: string;
    note: string;
    enabled: boolean;
    health: Health;
  }[];
  quotes: {
    id: string;
    name: string;
    markets: string[];
    note: string;
    health: Record<string, Health>;
  }[];
  mode: string;
};
const labels: Record<string, string> = {
  ok: "已获取",
  degraded: "报价延迟",
  failed: "请求失败",
  blocked: "访问受限",
  requires_access: "需授权接入",
  disabled: "未启用",
};
const names: Record<string, string> = { CN: "A 股", HK: "港股", US: "美股", CRYPTO: "加密货币" };
const time = (v?: string) =>
  v
    ? new Date(v).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "尚未检查";

export function SourcePanel({
  enabledNews,
  onNewsChange,
  quotes = false,
}: {
  enabledNews?: string[];
  onNewsChange?: (ids: string[]) => void;
  quotes?: boolean;
}) {
  const [data, setData] = useState<SourceData | null>(null),
    [error, setError] = useState(""),
    [expanded, setExpanded] = useState(!!onNewsChange),
    [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    try {
      setData(await api<SourceData>("/sources"));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 60000);
    return () => clearInterval(id);
  }, []);
  return (
    <section className="source-panel">
      <div className="source-panel-heading">
        <button
          className="text-link"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          <ChevronRight
            size={15}
            style={{ transform: expanded ? "rotate(90deg)" : undefined }}
          />
          {quotes ? "数据来源与运行状态" : "资讯来源"}
          {data && (
            <span>
              {data.news.filter((s) => s.enabled).length} 个已启用 ·{" "}
              {
                data.news.filter((s) => s.health.status === "ok" && s.enabled)
                  .length
              }{" "}
              个最近获取成功
            </span>
          )}
        </button>
        <button
          className="text-link"
          disabled={busy}
          onClick={() => void load()}
        >
          <RefreshCw size={13} className={busy ? "spin" : ""} />
          刷新状态
        </button>
      </div>
      {error && (
        <p className="hint" role="alert">
          {error}
        </p>
      )}
      {expanded && data && (
        <>
          <div className="source-grid">
            {data.news.map((source) => {
              const checked = (
                enabledNews ||
                data.news.filter((s) => s.enabled).map((s) => s.id)
              ).includes(source.id);
              const pending = !!onNewsChange && checked !== source.enabled;
              return (
                <article className="source-item" key={source.id}>
                  <div className="source-item-top">
                    {onNewsChange && (
                      <input
                        type="checkbox"
                        aria-label={"启用 " + source.name}
                        checked={checked}
                        onChange={(e) =>
                          onNewsChange(
                            e.target.checked
                              ? [...(enabledNews || []), source.id]
                              : (enabledNews || []).filter(
                                  (id) => id !== source.id,
                                ),
                          )
                        }
                      />
                    )}
                    <b>{source.name}</b>
                    <span
                      className={
                        "pill " +
                        (source.health.status === "ok"
                          ? "mint"
                          : source.health.status === "failed" ||
                              source.health.status === "requires_access"
                            ? "sand"
                            : "")
                      }
                    >
                      {pending
                        ? "待保存"
                        : labels[source.health.status || ""] || "等待首次获取"}
                    </span>
                  </div>
                  <small>
                    {source.kind} · {time(source.health.last_attempt)}
                  </small>
                  <p>{source.note}</p>
                  {source.health.last_error && (
                    <p className="source-error">{source.health.last_error}</p>
                  )}
                  {source.health.items !== undefined && (
                    <small>
                      最近解析 {source.health.items} 条 · 成功时间{" "}
                      {time(source.health.last_success)}
                    </small>
                  )}
                  <a href={source.url} target="_blank" rel="noreferrer">
                    打开原始来源 <ExternalLink size={11} />
                  </a>
                </article>
              );
            })}
          </div>
          {quotes && (
            <div className="quote-source-list">
              <h3>行情故障切换</h3>
              <p>
                自动模式：A 股依次使用腾讯、东方财富、Yahoo
                主备节点；港美股使用腾讯与
                Yahoo。异常源自动退避，缓存保留真实行情时间。
              </p>
              {data.quotes.map((source) => (
                <div key={source.id}>
                  <b>{source.name}</b>
                  <div>
                    {source.markets.map((m) => (
                      <span
                        key={m}
                        title={source.health[m]?.last_error || source.note}
                      >
                        {names[m]} ·{" "}
                        {labels[source.health[m]?.status || ""] || "等待获取"}
                      </span>
                    ))}
                  </div>
                  <small>{source.note}</small>
                </div>
              ))}
              <p>
                当前模式：{data.mode === "auto" ? "自动切换" : data.mode}
                。公开网站端点不提供持续可用性保证；无足够新鲜数据时暂停操作提示。报价、日线、分时可能来自不同来源，会分别标注。
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
