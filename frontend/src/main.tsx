import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  ExternalLink,
  Globe2,
  LayoutDashboard,
  Loader2,
  LockKeyhole,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Wallet,
  Waves,
  X,
} from "lucide-react";
import { api, AuthError } from "./api";
import { SourcePanel } from "./SourcePanel";
import type {
  PricePoint,
  Dashboard,
  Event,
  Market,
  News,
  Portfolio,
  Quote,
  Settings,
  Watch,
} from "./types";
import "./styles.css";

const marketName = { CN: "A 股", HK: "港股", US: "美股", CRYPTO: "加密货币" };
const marketFlag = { CN: "CN", HK: "HK", US: "US", CRYPTO: "₿" };
const kindName = (kind: string) => kind === "crypto" ? "加密现货" : kind === "etf" ? "ETF" : "股票";
const statusName: Record<string, string> = {
  open: "交易中",
  closed: "未开盘 / 已收盘",
  holiday: "休市",
  break: "午间休市",
  unknown: "日历待确认",
};
const nav = [
  { id: "overview", title: "投资总览", icon: LayoutDashboard },
  { id: "watchlist", title: "自选行情", icon: Activity },
  { id: "news", title: "财经资讯", icon: BookOpen },
  { id: "portfolio", title: "我的持仓", icon: Wallet },
  { id: "signals", title: "策略观察", icon: Sparkles },
  { id: "events", title: "提醒中心", icon: Bell },
  { id: "settings", title: "偏好设置", icon: Settings2 },
];
const fmt = (n?: number, digits = 2) =>
  n === undefined || n === null
    ? "—"
    : n.toLocaleString("zh-CN", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
const date = (v?: string) =>
  v
    ? new Date(
        v.endsWith("Z") || /[+-]\d\d:\d\d$/.test(v) ? v : v + "Z",
      ).toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      })
    : "尚未更新";
const pct = (v?: number) =>
  v === undefined ? "—" : `${v > 0 ? "+" : ""}${fmt(v)}%`;
function Pill({
  children,
  tone = "",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"pill " + tone}>{children}</span>;
}
function Empty({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Waves size={26} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = old;
    };
  }, [close]);
  return (
    <div className="overlay" onClick={close}>
      <section
        className={"modal " + (wide ? "wide" : "")}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-title">
          <h2>{title}</h2>
          <button aria-label="关闭" className="icon-btn" onClick={close}>
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
function Chart({
  bars,
  large = false,
}: {
  bars: PricePoint[];
  large?: boolean;
}) {
  if (bars.length < 2)
    return (
      <div className={"chart-empty " + (large ? "large" : "")}>
        暂无足够行情
      </div>
    );
  const values = bars.map((b) => b.close),
    low = Math.min(...values),
    high = Math.max(...values),
    span = high - low || 1;
  const points = values
    .map(
      (v, i) =>
        `${(i / (values.length - 1)) * 600},${130 - ((v - low) / span) * 110}`,
    )
    .join(" ");
  const up = values.at(-1)! >= values[0];
  return (
    <div
      className={"chart " + (large ? "large" : "")}
      role="img"
      aria-label={`价格从 ${fmt(values[0])} 变化至 ${fmt(values.at(-1))}`}
    >
      <svg viewBox="0 0 600 150" preserveAspectRatio="none">
        <path
          d="M0 20H600 M0 75H600 M0 130H600"
          stroke="currentColor"
          opacity=".08"
          strokeDasharray="3 5"
        />
        <polygon
          points={`0,150 ${points} 600,150`}
          fill={up ? "#219a7d" : "#ce7256"}
          opacity=".08"
        />
        <polyline
          points={points}
          fill="none"
          stroke={up ? "#219a7d" : "#ce7256"}
          strokeWidth={large ? 2 : 3}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      {large && (
        <div className="chart-labels">
          <span>{date(bars[0].time)}</span>
          <span>
            区间 {fmt(low)} – {fmt(high)}
          </span>
          <span>{date(bars.at(-1)!.time)}</span>
        </div>
      )}
    </div>
  );
}

function App() {
  const [page, setPage] = useState("overview"),
    [data, setData] = useState<Dashboard | null>(null),
    [auth, setAuth] = useState(false),
    [token, setToken] = useState("");
  const [toast, setToast] = useState(""),
    [busy, setBusy] = useState(""),
    [searchOpen, setSearchOpen] = useState(false),
    [detail, setDetail] = useState<Watch | null>(null),
    [sidebar, setSidebar] = useState(false),
    [error, setError] = useState("");
  async function reload() {
    try {
      const d = await api<Dashboard>("/dashboard");
      setData(d);
      setAuth(false);
      setError("");
    } catch (e) {
      if (e instanceof AuthError) setAuth(true);
      else setError((e as Error).message);
    }
  }
  useEffect(() => {
    void reload();
    const id = setInterval(() => void reload(), 60000);
    const listener = () => setAuth(true);
    const disconnected = (event: globalThis.Event) =>
      setError((event as CustomEvent<string>).detail);
    const connected = () => setError("");
    const reconnect = () => void reload();
    window.addEventListener("auth-required", listener);
    window.addEventListener("backend-unavailable", disconnected);
    window.addEventListener("backend-connected", connected);
    window.addEventListener("online", reconnect);
    return () => {
      clearInterval(id);
      window.removeEventListener("auth-required", listener);
      window.removeEventListener("backend-unavailable", disconnected);
      window.removeEventListener("backend-connected", connected);
      window.removeEventListener("online", reconnect);
    };
  }, []);
  useEffect(() => {
    if (toast) {
      const id = setTimeout(() => setToast(""), 7000);
      return () => clearTimeout(id);
    }
  }, [toast]);
  async function run(
    key: string,
    fn: () => Promise<unknown>,
    message = "已完成",
  ) {
    if (busy) return;
    setBusy(key);
    try {
      await fn();
      setToast(message);
      await reload();
    } catch (e) {
      setToast((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function refresh() {
    await run(
      "refresh",
      async () => {
        const r = await api<{
          status: string;
          message?: string;
          results?: { ok: boolean; error?: string }[];
        }>("/refresh", "POST");
        if (r.status === "busy") throw new Error(r.message);
        if (r.status === "partial")
          throw new Error(
            "部分行情未更新：" +
              (r.results?.find((x) => !x.ok)?.error || "请检查数据源"),
          );
      },
      "行情已更新",
    );
    await reload();
  }
  function go(p: string) {
    setPage(p);
    setSidebar(false);
  }
  if (auth)
    return (
      <main className="login">
        <div className="login-card">
          <div className="brand-icon">
            <Waves />
          </div>
          <small>INVEST WATCH</small>
          <h1>欢迎回到观澜</h1>
          <p>输入部署时配置的访问口令，打开你的投资观察台。</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sessionStorage.setItem("token", token);
              void reload();
            }}
          >
            <label>
              访问口令
              <input
                type="password"
                autoFocus
                autoComplete="current-password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                required
              />
            </label>
            <button className="primary" type="submit">
              进入观察台 <ArrowRight size={16} />
            </button>
          </form>
          <span className="muted">
            <LockKeyhole size={13} />
            口令仅保存在当前浏览器会话
          </span>
        </div>
      </main>
    );
  const d = data;
  return (
    <div className="app-shell">
      <aside className={"sidebar " + (sidebar ? "show" : "")}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            go("overview");
          }}
        >
          <div className="brand-icon">
            <Waves size={25} />
          </div>
          <div>
            <b>
              观澜<span> INVEST WATCH</span>
            </b>
            <small>让投资，回归从容。</small>
          </div>
        </a>
        <span className="nav-label">我的工作台</span>
        <nav>
          {nav.map((n) => (
            <button
              className={page === n.id ? "active" : ""}
              key={n.id}
              onClick={() => go(n.id)}
            >
              <n.icon size={18} />
              {n.title}
              {n.id === "watchlist" && !!d?.watchlist.length && (
                <small>{d.watchlist.length}</small>
              )}
              {n.id === "settings" && <ChevronRight size={14} />}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={20} />
          <b>独立判断，从容决策</b>
          <p>信息与规则辅助观察，每次操作仍由你决定。</p>
          <span>
            <i
              className={
                d?.worker_heartbeat &&
                Date.now() - new Date(d.worker_heartbeat).getTime() < 300000
                  ? "dot"
                  : "dot amber"
              }
            />
            {d?.worker_heartbeat &&
            Date.now() - new Date(d.worker_heartbeat).getTime() < 300000
              ? "后台监控运行中"
              : "后台监控尚未就绪"}
          </span>
        </div>
        <div className="account">
          <div className="avatar">我</div>
          <div>
            <b>个人投资空间</b>
            <small>私有部署 · v0.2.1</small>
          </div>
          <LockKeyhole size={15} />
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div>
            <button
              className="icon-btn mobile"
              onClick={() => setSidebar(!sidebar)}
              aria-label="菜单"
            >
              <Menu size={20} />
            </button>
            <span className="breadcrumb">
              工作台 <ChevronRight size={12} />{" "}
              <b>{nav.find((n) => n.id === page)?.title}</b>
            </span>
          </div>
          <div className="header-right">
            <span className="timezone">
              <Globe2 size={14} />
              北京时间
            </span>
            <button
              className="icon-btn"
              onClick={() => go("events")}
              aria-label="提醒中心"
            >
              <Bell size={19} />
            </button>
            <div className="avatar small">我</div>
          </div>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button onClick={() => void reload()}>重试</button>
          </div>
        )}
        {!d ? (
          error ? (
            <section className="card connection-failure" role="alert">
              <CircleHelp size={28} />
              <h2>暂时无法打开观察台</h2>
              <p>{error}</p>
              <p className="muted">
                本地开发请运行 scripts/start-local.ps1；Docker 部署请检查 web
                服务状态。
              </p>
              <button
                className="primary"
                onClick={() => {
                  setError("");
                  void reload();
                }}
              >
                重新连接
              </button>
            </section>
          ) : (
            <div className="loading">
              <Loader2 className="spin" />
              正在打开观察台…
            </div>
          )
        ) : (
          <div className="content">
            <div className="page-heading">
              <div>
                <div className="eyebrow">YOUR PERSONAL MARKET COMPASS</div>
                <h1>
                  {nav.find((n) => n.id === page)?.title}
                  <span>
                    {page === "overview"
                      ? "看见全局，专注重要的事。"
                      : page === "portfolio"
                        ? "用比例，管理每一次调整。"
                        : page === "news"
                          ? "把关注的世界，收进一个频道。"
                          : ""}
                  </span>
                </h1>
              </div>
              <div className="heading-actions">
                {["overview", "watchlist"].includes(page) && (
                  <>
                    <button
                      className="secondary"
                      disabled={!!busy}
                      onClick={() => void refresh()}
                    >
                      <RefreshCw
                        size={15}
                        className={busy === "refresh" ? "spin" : ""}
                      />
                      {busy === "refresh" ? "刷新中" : "刷新行情"}
                    </button>
                    <button
                      className="primary"
                      onClick={() => setSearchOpen(true)}
                    >
                      <Plus size={16} />
                      添加自选
                    </button>
                  </>
                )}
              </div>
            </div>
            {page === "overview" && (
              <>
                <div className="market-strip">
                  {d.markets.map((m) => (
                    <div key={m.market}>
                      <span className={"market-emblem " + m.market}>
                        {marketFlag[m.market]}
                      </span>
                      <div>
                        <b>{m.name}市场</b>
                        <small>
                          <i className={"dot " + (m.is_open ? "" : "gray")} />
                          {statusName[m.status]}
                        </small>
                      </div>
                      <div className="market-time">
                        <span>{m.market === "CRYPTO" ? "7×24 小时 · 每日观察" : "开盘后 30 分钟"}</span>
                        <b>
                          {m.daily_at
                            ? date(m.daily_at).split(" ").at(-1)
                            : "下一交易日"}
                        </b>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="overview-grid">
                  <section className="card focus-card">
                    <div className="card-heading">
                      <div>
                        <span className="eyebrow">WATCHLIST OVERVIEW</span>
                        <h2>关注的市场，尽在眼前</h2>
                      </div>
                      <Pill tone="light">{d.watchlist.length} 个自选</Pill>
                    </div>
                    {d.watchlist.length ? (
                      <>
                        <div className="focus-tickers">
                          {d.watchlist.slice(0, 3).map((w) => (
                            <button key={w.id} onClick={() => setDetail(w)}>
                              <small>{w.name}</small>
                              <b>{fmt(w.quote.price)}</b>
                              <span
                                className={
                                  (w.quote.change_pct || 0) >= 0 ? "up" : "down"
                                }
                              >
                                {pct(w.quote.change_pct)}
                                <small>
                                  {w.live ? "有效报价" : "待核对时效"}
                                </small>
                              </span>
                            </button>
                          ))}
                        </div>
                        <Chart
                          bars={
                            d.watchlist.find(
                              (w) => (w.quote.intraday?.length || 0) > 1,
                            )?.quote.intraday || []
                          }
                          large
                        />
                        <div className="focus-foot">
                          <span>
                            <i className="dot" />
                            图表：
                            {d.watchlist.find(
                              (w) => (w.quote.intraday?.length || 0) > 1,
                            )?.name || "暂无行情"}{" "}
                            · 最近交易日
                          </span>
                          <button onClick={() => go("watchlist")}>
                            查看全部 <ArrowRight size={14} />
                          </button>
                        </div>
                      </>
                    ) : (
                      <div className="welcome">
                        <span className="welcome-orbit">
                          <Activity size={35} />
                        </span>
                        <h3>从你的第一个自选开始</h3>
                        <p>
                          股票与 ETF、三地市场、重要资讯。
                          <br />
                          让分散的信息，在这里汇合。
                        </p>
                        <button
                          className="light-button"
                          onClick={() => setSearchOpen(true)}
                        >
                          搜索关注的标的 <ArrowRight size={15} />
                        </button>
                        <div className="welcome-markets">
                          A 股 <span>／</span> 港股 <span>／</span> 美股
                        </div>
                      </div>
                    )}
                  </section>
                  <section className="card allocation-card">
                    <div className="card-heading">
                      <div>
                        <span className="eyebrow">MY ALLOCATION</span>
                        <h2>每一份，都心中有数</h2>
                      </div>
                      <Wallet size={19} />
                    </div>
                    <Allocation portfolio={d.portfolio} watches={d.watchlist} />
                    <button
                      className="text-link"
                      onClick={() => go("portfolio")}
                    >
                      管理持仓比例 <ArrowRight size={14} />
                    </button>
                  </section>
                </div>
                <div className="summary-row">
                  <div>
                    <div className="summary-icon mint">
                      <Activity size={19} />
                    </div>
                    <span>
                      有效盘中报价
                      <b>
                        {d.watchlist.filter((w) => w.live).length}
                        <small> / {d.watchlist.length} 个自选</small>
                      </b>
                    </span>
                  </div>
                  <div>
                    <div className="summary-icon sand">
                      <ShieldCheck size={19} />
                    </div>
                    <span>
                      分析模式
                      <b>
                        {d.mode.strategy ? "程序策略" : "行情观察"}
                        <small>
                          {d.mode.ai ? " + AI 辅助" : " · AI 未启用"}
                        </small>
                      </b>
                    </span>
                  </div>
                  <div>
                    <div className="summary-icon lavender">
                      <Clock3 size={19} />
                    </div>
                    <span>
                      持仓更新时间
                      <b>
                        {date(d.portfolio.updated_at)}
                        <small>手动快照</small>
                      </b>
                    </span>
                  </div>
                </div>
                <div className="bottom-grid">
                  <section className="card">
                    <div className="card-heading">
                      <h2>
                        我的自选 <small>WATCHING</small>
                      </h2>
                      <button
                        className="text-link"
                        onClick={() => go("watchlist")}
                      >
                        全部 <ArrowRight size={14} />
                      </button>
                    </div>
                    <WatchTable
                      watches={d.watchlist.slice(0, 5)}
                      onDetail={setDetail}
                      compact
                    />
                  </section>
                  <section className="card">
                    <div className="card-heading">
                      <h2>观察动态</h2>
                      <button
                        className="text-link"
                        onClick={() => go("events")}
                      >
                        更多 <ArrowRight size={14} />
                      </button>
                    </div>
                    {d.events.length ? (
                      <div className="timeline">
                        {d.events.slice(0, 4).map((e) => (
                          <div key={e.id}>
                            <i />
                            <div>
                              <span>{date(e.created)}</span>
                              <b>{e.title}</b>
                              {e.payload.status && (
                                <small>
                                  {e.payload.status === "ok"
                                    ? "已完成"
                                    : e.payload.status === "failed"
                                      ? "处理失败"
                                      : "处理中"}
                                </small>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <Empty
                        title="平静，也是好消息"
                        text="风险提醒、每日观察与分析记录将汇集在这里。"
                      />
                    )}
                  </section>
                </div>
              </>
            )}
            {page === "watchlist" && (
              <WatchlistPage
                watches={d.watchlist}
                onDetail={setDetail}
                onAdd={() => setSearchOpen(true)}
                run={run}
              />
            )}
            {page === "portfolio" && (
              <PortfolioPage
                data={d}
                onSave={(p) =>
                  run(
                    "portfolio",
                    () => api("/portfolio", "PUT", p),
                    "持仓比例已保存",
                  )
                }
                busy={!!busy}
              />
            )}
            {page === "news" && (
              <NewsPage
                keywords={d.keywords}
                notify={setToast}
                settings={() => go("settings")}
              />
            )}
            {page === "signals" && (
              <section>
                <div className="info-banner">
                  <ShieldCheck size={19} />
                  <div>
                    <b>
                      {d.mode.strategy
                        ? "程序策略已启用"
                        : "当前为行情观察模式"}
                    </b>
                    <p>
                      完整日线判断趋势，盘中报价校验时效；持仓限制优先。
                      {!d.mode.strategy && "在偏好设置中可开启程序策略。"}
                    </p>
                  </div>
                  <button className="text-link" onClick={() => go("settings")}>
                    配置 <ArrowRight size={14} />
                  </button>
                </div>
                <div className="signal-grid">
                  {d.watchlist.map((w) => (
                    <section className="card signal-card" key={w.id}>
                      <div className="card-heading">
                        <div>
                          <h2>{w.name}</h2>
                          <small>
                            {w.symbol} · {marketName[w.market]}
                          </small>
                        </div>
                        <Pill
                          tone={
                            w.signal.delta > 0
                              ? "mint"
                              : w.signal.delta < 0
                                ? "sand"
                                : ""
                          }
                        >
                          {w.signal.action_label}
                        </Pill>
                      </div>
                      <div className="signal-number">
                        {w.signal.delta
                          ? `${w.signal.delta > 0 ? "+" : ""}${w.signal.delta}`
                          : "—"}
                        <small>
                          {w.signal.delta ? "份建议调整" : "暂无调整"}
                        </small>
                      </div>
                      <ul>
                        {w.signal.reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                      {w.signal.metrics && (
                        <div className="metric-chips">
                          <span>RSI {w.signal.metrics.rsi}</span>
                          <span>MA20 {fmt(Number(w.signal.metrics.ma20))}</span>
                          <span>ATR {fmt(Number(w.signal.metrics.atr))}</span>
                        </div>
                      )}
                      <p className="muted">{w.signal.constraints.join("；")}</p>
                      <button
                        className="text-link"
                        onClick={() => setDetail(w)}
                      >
                        查看依据 <ArrowRight size={14} />
                      </button>
                    </section>
                  ))}
                </div>
                {!d.watchlist.length && (
                  <Empty
                    title="先添加关注标的"
                    text="拥有足够的完整日 K 线和有效行情后，程序才能分析。"
                    action={
                      <button
                        className="primary"
                        onClick={() => setSearchOpen(true)}
                      >
                        添加自选
                      </button>
                    }
                  />
                )}
                <section className="card ai-panel">
                  <div>
                    <Sparkles size={23} />
                    <h2>让信息，多一层理解</h2>
                    <p>
                      仅在你开启时，AI
                      才结合资讯、行情和持仓比例分析。不会发送资产金额。
                    </p>
                  </div>
                  <button
                    className="primary"
                    disabled={!!busy || !d.mode.ai}
                    onClick={() =>
                      void run(
                        "ai",
                        async () => {
                          await api("/ai/analyze", "POST");
                          go("events");
                        },
                        "分析已保存到提醒中心",
                      )
                    }
                  >
                    {busy === "ai" ? (
                      <Loader2 className="spin" size={16} />
                    ) : (
                      <Sparkles size={16} />
                    )}
                    生成 AI 分析
                  </button>
                  {!d.mode.ai && (
                    <span className="muted">请先在设置中配置并启用 AI</span>
                  )}
                </section>
              </section>
            )}
            {page === "events" && (
              <EventsPage notify={setToast} watches={d.watchlist} />
            )}
            {page === "settings" && (
              <SettingsPage notify={setToast} reload={reload} />
            )}
            <footer>
              <span>观澜 · 把注意力留给真正重要的事</span>
              <span>
                规则与 AI 仅辅助判断，不保证收益。数据时间以各来源标注为准。
              </span>
            </footer>
          </div>
        )}
      </main>
      {toast && (
        <div className="toast" role="status">
          <CircleHelp size={18} />
          <span>{toast}</span>
          <button aria-label="关闭消息" onClick={() => setToast("")}>
            <X size={15} />
          </button>
        </div>
      )}
      {searchOpen && (
        <SearchModal
          close={() => setSearchOpen(false)}
          existing={d?.watchlist || []}
          onAdded={() => void reload()}
          notify={setToast}
        />
      )}
      {detail && (
        <DetailModal
          watch={d?.watchlist.find((w) => w.id === detail.id) || detail}
          close={() => setDetail(null)}
          notify={setToast}
          refresh={() => void reload()}
        />
      )}
    </div>
  );
}

function Allocation({
  portfolio: p,
  watches,
}: {
  portfolio: Portfolio;
  watches: Watch[];
}) {
  const colors = ["#5c8e7d", "#bfa984", "#7c8ca3", "#a59ab5", "#b77e6c"];
  const parts = p.positions
    .filter((x) => Number(x.shares) > 0)
    .map((x, i) => ({
      label: watches.find((w) => w.id === x.watch_id)?.name || x.watch_id,
      value: Number(x.shares),
      color: colors[i % colors.length],
    }));
  parts.push({ label: "现金", value: Number(p.cash), color: "#e0e6df" });
  let progress = 0;
  const gradient = parts
    .map((p) => {
      const start = progress;
      progress += p.value;
      return `${p.color} ${start}% ${progress}%`;
    })
    .join(",");
  return (
    <>
      <div
        className="donut"
        style={{ background: `conic-gradient(${gradient})` }}
      >
        <div>
          <strong>
            100<small>份</small>
          </strong>
          <span>总资金比例</span>
        </div>
      </div>
      <div className="allocation-legend">
        {parts.map((p, i) => (
          <div key={i}>
            <i style={{ background: p.color }} />
            <span>{p.label}</span>
            <b>
              {p.value}
              <small> 份</small>
            </b>
          </div>
        ))}
      </div>
    </>
  );
}

function WatchTable({
  watches,
  onDetail,
  compact = false,
}: {
  watches: Watch[];
  onDetail: (w: Watch) => void;
  compact?: boolean;
}) {
  return watches.length ? (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>标的 / 市场</th>
            <th>最新价</th>
            <th>涨跌幅</th>
            {!compact && (
              <>
                <th>最近交易日</th>
                <th>数据状态</th>
                <th>监控阈值</th>
              </>
            )}
            <th />
          </tr>
        </thead>
        <tbody>
          {watches.map((w) => (
            <tr key={w.id} onClick={() => onDetail(w)}>
              <td>
                <div className="stock-cell">
                  <span className={"stock-mark " + w.market}>
                    {w.symbol.slice(0, 2)}
                  </span>
                  <div>
                    <b>{w.name}</b>
                    <small>
                      {w.symbol} · {marketName[w.market]}
                      {w.kind === "etf" ? " · ETF" : ""}
                    </small>
                  </div>
                </div>
              </td>
              <td className="numeric">
                {fmt(w.quote.price)}
                <small>{w.quote.currency}</small>
              </td>
              <td>
                <span
                  className={
                    "change " + ((w.quote.change_pct || 0) >= 0 ? "up" : "down")
                  }
                >
                  {(w.quote.change_pct || 0) >= 0 ? (
                    <ArrowUpRight size={13} />
                  ) : (
                    <ArrowDownRight size={13} />
                  )}{" "}
                  {pct(w.quote.change_pct)}
                </span>
              </td>
              {!compact && (
                <>
                  <td>
                    <div className="sparkline">
                      <Chart bars={w.quote.intraday || []} />
                    </div>
                  </td>
                  <td>
                    <span className={"data-status " + (w.live ? "" : "muted")}>
                      <i className={"dot " + (w.live ? "" : "amber")} />
                      {w.error
                        ? "更新失败"
                        : w.live
                          ? "有效盘中报价"
                          : w.quote.price
                            ? "历史 / 延迟"
                            : "等待刷新"}
                    </span>
                    <small className="subtext">{date(w.quote.as_of)}</small>
                  </td>
                  <td>±{w.threshold}%</td>
                </>
              )}
              <td>
                <button className="icon-btn" aria-label={"查看" + w.name}>
                  <ChevronRight size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty
      title="还没有关注的标的"
      text="添加你关心的股票或 ETF，开启每日观察。"
    />
  );
}
function WatchlistPage({
  watches,
  onDetail,
  onAdd,
  run,
}: {
  watches: Watch[];
  onDetail: (w: Watch) => void;
  onAdd: () => void;
  run: (
    key: string,
    fn: () => Promise<unknown>,
    message?: string,
  ) => Promise<void>;
}) {
  const [market, setMarket] = useState("ALL"),
    [q, setQ] = useState("");
  return (
    <>
      <div className="toolbar">
        <div className="tabs">
          {["ALL", "CN", "HK", "US", "CRYPTO"].map((m) => (
            <button
              key={m}
              className={market === m ? "selected" : ""}
              onClick={() => setMarket(m)}
            >
              {m === "ALL" ? "全部市场" : marketName[m as Market]}
            </button>
          ))}
        </div>
        <div className="search-input">
          <Search size={16} />
          <input
            aria-label="筛选自选"
            placeholder="筛选名称或代码"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      <section className="card">
        <WatchTable
          watches={watches.filter(
            (w) =>
              (market === "ALL" || w.market === market) &&
              `${w.name}${w.symbol}`.toLowerCase().includes(q.toLowerCase()),
          )}
          onDetail={onDetail}
        />
      </section>
      <div className="info-banner">
        <CircleHelp size={18} />
        <p>
          涨跌幅以昨收为基准。盘中监控每分钟轮询；仅使用交易时段内且 5
          分钟内的报价。免费实验性数据源可能延迟或不可用。
        </p>
        <button className="text-link" onClick={onAdd}>
          添加标的 <Plus size={14} />
        </button>
      </div>
      <details className="manage-list">
        <summary>管理订阅与异常阈值</summary>
        {watches.map((w) => (
          <div key={w.id}>
            <span>
              {w.name} <small>{w.symbol}</small>
            </span>
            <label>
              涨跌阈值{" "}
              <input
                type="number"
                aria-label={w.name + "阈值"}
                min="0.5"
                max="50"
                step="0.5"
                defaultValue={w.threshold}
                onBlur={(e) => {
                  const value = Number(e.target.value);
                  if (value !== w.threshold)
                    void run(
                      "threshold",
                      () =>
                        api(
                          `/watchlist/${encodeURIComponent(w.id)}?threshold=${value}`,
                          "PATCH",
                        ),
                      "阈值已更新",
                    );
                }}
              />{" "}
              %
            </label>
            <button
              className="icon-btn danger"
              aria-label={"移除" + w.name}
              onClick={() =>
                void run(
                  "remove",
                  () => api("/watchlist/" + encodeURIComponent(w.id), "DELETE"),
                  "已移除自选",
                )
              }
            >
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </details>
    </>
  );
}

function SearchModal({
  close,
  existing,
  onAdded,
  notify,
}: {
  close: () => void;
  existing: Watch[];
  onAdded: () => void;
  notify: (s: string) => void;
}) {
  const [market, setMarket] = useState<Market>("CN"),
    [q, setQ] = useState(""),
    [items, setItems] = useState<
      {
        symbol: string;
        name: string;
        market: Market;
        exchange: string;
        kind: string;
      }[]
    >([]),
    [warning, setWarning] = useState(""),
    [searchError, setSearchError] = useState(""),
    [searchAttempt, setSearchAttempt] = useState(0),
    [busy, setBusy] = useState(false),
    [manual, setManual] = useState(false),
    [symbol, setSymbol] = useState(""),
    [name, setName] = useState(""),
    [kind, setKind] = useState("etf");
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setItems([]);
    setWarning("");
    setSearchError("");
    setBusy(true);
    const timer = setTimeout(() => {
      setBusy(true);
      api<{ items: typeof items; warning?: string }>(
        "/search?market=" + market + "&q=" + encodeURIComponent(q),
        "GET",
        undefined,
        { signal: controller.signal },
      )
        .then((r) => {
          if (!cancelled) {
            setItems(r.items);
            setWarning(r.warning || "");
            setSearchError("");
          }
        })
        .catch((e) => {
          if (!cancelled) {
            setItems([]);
            setSearchError(e.message);
          }
        })
        .finally(() => {
          if (!cancelled) setBusy(false);
        });
    }, 300);
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [q, market, searchAttempt]);
  async function add(item: (typeof items)[number]) {
    setBusy(true);
    try {
      await api("/watchlist", "POST", item);
      notify("已添加 " + item.name + "，点击刷新行情获取价格");
      onAdded();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="添加关注标的" close={close}>
      <div className="tabs wide-tabs">
        {(["CN", "HK", "US", "CRYPTO"] as Market[]).map((m) => (
          <button
            className={market === m ? "selected" : ""}
            key={m}
            onClick={() => setMarket(m)}
          >
            {marketName[m]}
          </button>
        ))}
      </div>
      <div className="search-input big">
        <Search size={19} />
        <input
          placeholder="搜索名称、代码或英文名"
          aria-label="搜索标的"
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {busy && <Loader2 size={17} className="spin" />}
      </div>
      {warning && (
        <div className="hint" role="status">
          {warning}
          <button
            className="text-link"
            onClick={() => setSearchAttempt((n) => n + 1)}
          >
            重试在线搜索
          </button>
        </div>
      )}
      {searchError && (
        <div className="request-error" role="alert">
          <b>搜索未完成</b>
          <p>{searchError}</p>
          <button
            className="secondary"
            onClick={() => setSearchAttempt((n) => n + 1)}
          >
            重试搜索
          </button>
        </div>
      )}
      {busy && (
        <p className="muted" role="status">
          正在搜索{marketName[market]}标的…
        </p>
      )}
      <div className="search-results">
        {items.map((item) => (
          <div key={item.symbol}>
            <div>
              <b>{item.name}</b>
              <small>
                {item.symbol} · {kindName(item.kind)}
              </small>
            </div>
            <button
              disabled={
                busy ||
                existing.some(
                  (w) => w.symbol === item.symbol && w.market === market,
                )
              }
              className="secondary"
              aria-label={"订阅 " + item.name}
              onClick={() => void add(item)}
            >
              {existing.some(
                (w) => w.symbol === item.symbol && w.market === market,
              ) ? (
                <Check size={16} />
              ) : (
                <Plus size={16} />
              )}
            </button>
          </div>
        ))}
        {!items.length && !busy && !searchError && (
          <p className="muted">没有找到结果，可尝试完整代码或手动添加。</p>
        )}
      </div>
      <button className="text-link" onClick={() => setManual(!manual)}>
        手动添加完整代码 <ChevronRight size={14} />
      </button>
      {manual && (
        <form
          className="manual-form"
          onSubmit={(e) => {
            e.preventDefault();
            void add({
              symbol: symbol.toUpperCase().trim(),
              name,
              market,
              kind: market === "CRYPTO" ? "crypto" : kind,
              exchange: market,
            });
          }}
        >
          <label>
            完整代码
            <input
              required
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder={
                market === "CN"
                  ? "513100.SS / 159915.SZ"
                  : market === "HK"
                    ? "0700.HK"
                    : market === "CRYPTO" ? "BTC-USDT / ETH-USD" : "QQQ"
              }
            />
          </label>
          <label>
            显示名称
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={160}
            />
          </label>
          <label>
            类型
            <select value={market === "CRYPTO" ? "crypto" : kind} disabled={market === "CRYPTO"} onChange={(e) => setKind(e.target.value)}>
              {market === "CRYPTO" && <option value="crypto">加密现货</option>}
              <option value="etf">ETF</option>
              <option value="stock">股票</option>
            </select>
          </label>
          <button className="primary" disabled={busy}>
            添加
          </button>
        </form>
      )}
      <p className="muted modal-foot">
        目录用于查找标的，不包含模拟价格。请核对代码和产品名称。
      </p>
    </Modal>
  );
}

function DetailModal({
  watch: w,
  close,
  notify,
  refresh,
}: {
  watch: Watch;
  close: () => void;
  notify: (s: string) => void;
  refresh: () => void;
}) {
  const [q, setQ] = useState<Quote>(w.quote),
    [period, setPeriod] = useState("intraday");
  useEffect(() => {
    api<Quote>("/watchlist/" + encodeURIComponent(w.id) + "/history")
      .then(setQ)
      .catch((e) => notify(e.message));
  }, [w.id]);
  return (
    <Modal title={w.name} close={close} wide>
      <div className="detail-top">
        <div>
          <small>
            {w.symbol} · {marketName[w.market]} ·{" "}
            {kindName(w.kind)}
          </small>
          <h1>
            {fmt(q.price)}{" "}
            <span className={(q.change_pct || 0) >= 0 ? "up" : "down"}>
              {pct(q.change_pct)}
            </span>
          </h1>
        </div>
        <Pill tone={w.live ? "mint" : "sand"}>
          {w.live ? "有效盘中报价" : "请核对数据时效"}
        </Pill>
      </div>
      {w.error && <p className="hint">{w.error}</p>}
      <div className="tabs">
        <button
          className={period === "intraday" ? "selected" : ""}
          onClick={() => setPeriod("intraday")}
        >
          {w.market === "CRYPTO" ? "近期现货 · 5 分钟" : "最近交易日 · 5 分钟"}
        </button>
        <button
          className={period === "history" ? "selected" : ""}
          onClick={() => setPeriod("history")}
        >
          历史日线
        </button>
      </div>
      <Chart
        large
        bars={(period === "intraday" ? q.intraday : q.history) || []}
      />
      <div className="detail-source">
        {q.source || "尚无行情"} · 报价时间 {date(q.as_of)}
        <p>
          日线来源：{q.history_source || q.source || "尚无数据"} · 分时来源：
          {q.intraday_source || "尚无数据"}
        </p>
        <p>{q.delay_note}</p>
        {q.change_basis && <p>涨跌幅基准：{q.change_basis} · 计价 {q.currency}</p>}
      </div>
      <div className="detail-analysis">
        <h3>
          程序观察 <Pill>{w.signal.action_label}</Pill>
        </h3>
        {w.signal.reasons.map((r, i) => (
          <p key={i}>{r}</p>
        ))}
        {w.signal.metrics && (
          <div className="metric-grid">
            {[
              ["MA20", "ma20"],
              ["MA60", "ma60"],
              ["RSI", "rsi"],
              ["MACD", "macd"],
              ["ATR", "atr"],
              ["量比（日线）", "volume_ratio"],
            ].map(([n, k]) => (
              <div key={k}>
                <small>{n}</small>
                <b>
                  {w.signal.metrics?.[k] == null
                    ? "—"
                    : fmt(Number(w.signal.metrics[k]))}
                </b>
              </div>
            ))}
          </div>
        )}
        <p className="muted">{w.signal.constraints.join("；")}</p>
        <small className="muted">
          规则版本 {w.signal.rule_version} ·
          指标仅采用完整日线，不代表预测成功概率。
        </small>
      </div>
      <div className="modal-actions">
        <button className="secondary" onClick={close}>
          关闭
        </button>
        <button
          className="primary"
          onClick={async () => {
            try {
              const r = await api<{ status: string; message?: string }>(
                "/refresh",
                "POST",
              );
              notify(
                r.status === "busy" ? r.message || "刷新中" : "行情刷新完成",
              );
              refresh();
            } catch (e) {
              notify((e as Error).message);
            }
          }}
        >
          <RefreshCw size={15} />
          刷新行情
        </button>
      </div>
    </Modal>
  );
}

function PortfolioPage({
  data: d,
  onSave,
  busy,
}: {
  data: Dashboard;
  onSave: (p: Portfolio) => void;
  busy: boolean;
}) {
  const [p, setP] = useState<Portfolio>(structuredClone(d.portfolio)),
    [capital, setCapital] = useState("");
  useEffect(() => setP(structuredClone(d.portfolio)), [d.portfolio.revision]);
  const sum =
      Number(p.cash) + p.positions.reduce((a, x) => a + Number(x.shares), 0),
    valid = Math.abs(sum - 100) < 0.00001;
  const update = (index: number, key: string, value: string) =>
    setP({
      ...p,
      positions: p.positions.map((x, i) =>
        i === index
          ? { ...x, [key]: key === "target" && value === "" ? null : value }
          : x,
      ),
    });
  return (
    <div className="portfolio-layout">
      <section className="card">
        <div className="card-heading">
          <div>
            <h2>我的 100 份资产</h2>
            <small>不填写金额，只管理比例。保存不会执行交易。</small>
          </div>
          <Pill tone={valid ? "mint" : "sand"}>合计 {fmt(sum)} / 100 份</Pill>
        </div>
        <div className="table-wrap">
          <table className="portfolio-table">
            <thead>
              <tr>
                <th>资产</th>
                <th>当前份额</th>
                <th>目标（可选）</th>
                <th>上限</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {p.positions.map((x, i) => (
                <tr key={x.watch_id}>
                  <td>
                    <b>
                      {d.watchlist.find((w) => w.id === x.watch_id)?.name ||
                        x.watch_id}
                    </b>
                    <small className="subtext">{x.watch_id}</small>
                  </td>
                  <td>
                    <input
                      aria-label={"当前份额" + i}
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={x.shares}
                      onChange={(e) => update(i, "shares", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      aria-label={"目标份额" + i}
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={x.target ?? ""}
                      placeholder="不限制"
                      onChange={(e) => update(i, "target", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      aria-label={"仓位上限" + i}
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={x.cap}
                      onChange={(e) => update(i, "cap", e.target.value)}
                    />
                  </td>
                  <td>
                    <button
                      className="icon-btn danger"
                      aria-label="移除仓位"
                      onClick={() =>
                        setP({
                          ...p,
                          positions: p.positions.filter((_, n) => n !== i),
                        })
                      }
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
              <tr>
                <td>
                  <b>现金</b>
                  <small className="subtext">保留下一次选择的空间</small>
                </td>
                <td>
                  <input
                    aria-label="现金份额"
                    type="number"
                    min="0"
                    max="100"
                    step="0.01"
                    value={p.cash}
                    onChange={(e) => setP({ ...p, cash: e.target.value })}
                  />
                </td>
                <td colSpan={3}>
                  <button
                    className="text-link"
                    onClick={() =>
                      setP({
                        ...p,
                        cash:
                          Math.round(
                            (100 -
                              p.positions.reduce(
                                (a, x) => a + Number(x.shares),
                                0,
                              )) *
                              100,
                          ) / 100,
                      })
                    }
                  >
                    用剩余份额填充现金
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="portfolio-add">
          <select
            aria-label="添加持仓标的"
            value=""
            onChange={(e) => {
              if (e.target.value)
                setP({
                  ...p,
                  positions: [
                    ...p.positions,
                    {
                      watch_id: e.target.value,
                      shares: 0,
                      target: null,
                      cap: 40,
                    },
                  ],
                });
            }}
          >
            <option value="">＋ 从自选添加仓位</option>
            {d.watchlist
              .filter((w) => !p.positions.some((x) => x.watch_id === w.id))
              .map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} ({w.symbol})
                </option>
              ))}
          </select>
          <p className="muted">
            还没买入的标的可设为 0 份，让程序知道允许的仓位上限。
          </p>
        </div>
        <div className="form-grid constraints">
          <label>
            最低现金（份）
            <input
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={p.min_cash}
              onChange={(e) => setP({ ...p, min_cash: e.target.value })}
            />
          </label>
          <label>
            单次调整上限（份）
            <input
              type="number"
              min="0.01"
              max="5"
              step="0.01"
              value={p.max_step}
              onChange={(e) => setP({ ...p, max_step: e.target.value })}
            />
          </label>
          <label>
            风险偏好
            <select
              value={p.risk}
              onChange={(e) => setP({ ...p, risk: e.target.value })}
            >
              <option value="conservative">稳健 · 单次加仓最多 0.5 份</option>
              <option value="balanced">均衡</option>
              <option value="growth">成长</option>
            </select>
          </label>
          <label>
            投资周期
            <select
              value={p.horizon}
              onChange={(e) => setP({ ...p, horizon: e.target.value })}
            >
              <option value="short">短期观察</option>
              <option value="medium">中期持有</option>
              <option value="long">长期配置</option>
            </select>
          </label>
        </div>
        <div className="form-bottom">
          <span className={valid ? "muted" : "down"}>
            {valid
              ? "合计正确，可保存"
              : `请调整至 100 份，当前差额 ${fmt(100 - sum)} 份`}
          </span>
          <button
            className="primary"
            disabled={busy || !valid}
            onClick={() => onSave(p)}
          >
            {busy ? (
              <Loader2 size={16} className="spin" />
            ) : (
              <Check size={16} />
            )}
            保存持仓快照
          </button>
        </div>
      </section>
      <div>
        <section className="card allocation-card">
          <div className="card-heading">
            <h2>配置预览</h2>
            <Pill>100 份制</Pill>
          </div>
          {valid ? (
            <Allocation portfolio={p} watches={d.watchlist} />
          ) : (
            <Empty
              title="等待份额平衡"
              text="持仓与现金合计 100 份后显示预览。"
            />
          )}
          <p className="muted">
            手动快照不会自动反映涨跌带来的比例变化，请定期核对更新。
          </p>
        </section>
        <section className="card calculator">
          <h3>1 份，是多少钱？</h3>
          <p>仅在当前页面临时换算，输入金额不会上传或保存。</p>
          <label>
            总资金（可选）
            <input
              type="number"
              min="0"
              placeholder="例如 1000000"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
            />
          </label>
          <b>
            {capital ? fmt(Number(capital) / 100) : "—"}
            <small> / 份</small>
          </b>
        </section>
      </div>
    </div>
  );
}

function NewsPage({
  keywords,
  notify,
  settings,
}: {
  keywords: string[];
  notify: (s: string) => void;
  settings: () => void;
}) {
  const [items, setItems] = useState<News[]>([]),
    [q, setQ] = useState(""),
    [only, setOnly] = useState(false),
    [crypto, setCrypto] = useState(false),
    [loading, setLoading] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const requestId = useRef(0);
  async function load() {
    const id = ++requestId.current;
    setLoading(true);
    try {
      const result = await api<{ items: News[] }>(
            "/news?q=" + encodeURIComponent(q) + "&subscribed=" + only + "&topic=" + (crypto ? "crypto" : ""),
          );
      if (id !== requestId.current) return;
      setItems(result.items);
      setError("");
    } catch (e) {
      if (id === requestId.current) setError((e as Error).message);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }
  useEffect(() => {
    const id = setTimeout(() => void load(), 250);
    return () => {clearTimeout(id);requestId.current++;};
  }, [q, only, crypto]);
  return (
    <>
      <div className="toolbar">
        <div className="tabs">
          <button
            className={!only && !crypto ? "selected" : ""}
            onClick={() => {setOnly(false);setCrypto(false);}}
          >
            全部资讯
          </button>
          <button
            className={only ? "selected" : ""}
            onClick={() => {setOnly(true);setCrypto(false);}}
          >
            我的方向
          </button>
          <button className={crypto ? "selected" : ""} onClick={() => {setCrypto(true);setOnly(false);}}>加密货币</button>
        </div>
        <div className="row">
          <div className="search-input">
            <Search size={16} />
            <input
              aria-label="搜索资讯"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="搜索标题或来源"
            />
          </div>
          <button
            className="secondary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const r = await api<{
                  status: string;
                  added: number;
                  failures?: { source: string; error: string }[];
                }>("/news/refresh", "POST");
                notify(
                  r.status === "cached"
                    ? "来源仍在各自刷新间隔内，请稍后再试"
                    : r.failures?.length
                      ? "部分资讯源失败：" +
                        r.failures
                          .map((f) => f.source + " " + f.error)
                          .join("；")
                      : `已新增 ${r.added} 条资讯`,
                );
                await load();
              } catch (e) {
                notify((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <RefreshCw size={15} className={busy ? "spin" : ""} />
            获取资讯
          </button>
        </div>
      </div>
      <SourcePanel />
      <div className="keyword-bar">
        <span>关注方向</span>
        {keywords.slice(0, 8).map((k) => (
          <button key={k} onClick={() => setQ(k)}>
            {k}
          </button>
        ))}
        <button className="text-link" onClick={settings}>
          编辑订阅 <Plus size={13} />
        </button>
      </div>
      {error && <p className="hint">{error}</p>}
      {loading && <p className="muted" role="status">正在加载资讯…</p>}
      <section className="card news-list">
        {items.length ? (
          items.map((a, i) => (
            <article key={a.id}>
              <div className="news-index">{String(i + 1).padStart(2, "0")}</div>
              <div>
                <div className="news-meta">
                  <span>{a.source}</span>
                  <span>
                    {a.published ? date(a.published) : "发布时间未知"}
                  </span>
                </div>
                <a href={a.url} target="_blank" rel="noreferrer">
                  {a.title}
                  <ExternalLink size={14} />
                </a>
                <div className="news-tags">
                  {a.tags.map((t) => (
                    <Pill key={t}>{t}</Pill>
                  ))}
                  {!!a.tags.length && <small>关键词匹配</small>}
                </div>
              </div>
            </article>
          ))
        ) : !loading && !error ? (
          <Empty
            title="把重要资讯，汇集到这里"
            text="点击获取资讯，或在偏好设置中添加你信任的 RSS / Atom 源。只展示来源标题与链接，不用 AI 生成新闻。"
            action={
              <button className="secondary" onClick={settings}>
                配置资讯来源 <ArrowRight size={14} />
              </button>
            }
          />
        ) : null}
      </section>
    </>
  );
}

function EventsPage({
  notify,
  watches,
}: {
  notify: (s: string) => void;
  watches: Watch[];
}) {
  const [events, setEvents] = useState<Event[]>([]),
    [deliveries, setDeliveries] = useState<
      { id: string; status: string; attempts: number; error?: string }[]
    >([]),
    [filter, setFilter] = useState("all");
  useEffect(() => {
    api<{ items: Event[]; deliveries: typeof deliveries }>("/events")
      .then((r) => {
        setEvents(r.items);
        setDeliveries(r.deliveries);
      })
      .catch((e) => notify(e.message));
  }, []);
  const names: Record<string, string> = {
    all: "全部记录",
    alert: "风险事件",
    daily: "每日观察",
    ai: "AI 分析",
    portfolio: "持仓变更",
    data: "数据状态",
  };
  return (
    <>
      <div className="tabs event-tabs">
        {Object.entries(names).map(([k, v]) => (
          <button
            key={k}
            className={filter === k ? "selected" : ""}
            onClick={() => setFilter(k)}
          >
            {v}
          </button>
        ))}
      </div>
      <section className="event-list">
        {events
          .filter((e) => filter === "all" || e.kind === filter)
          .map((e) => {
            const delivery = deliveries.find((x) => x.id === e.id);
            return (
              <section className="card event-card" key={e.id}>
                <div className="card-heading">
                  <div>
                    <small>
                      {date(e.created)} · {names[e.kind] || "系统记录"}
                    </small>
                    <h2>{e.title}</h2>
                  </div>
                  <Pill tone={delivery?.status === "failed" ? "sand" : ""}>
                    {delivery
                      ? {
                          sent: "已推送",
                          pending: "等待推送",
                          sending: "发送中",
                          expired: "已过期",
                          failed: "推送失败",
                          disabled: "通知已关闭",
                        }[delivery.status] || delivery.status
                      : "站内记录"}
                  </Pill>
                </div>
                {e.payload.error && <p className="hint">{e.payload.error}</p>}
                {e.payload.failures?.map((f, i) => (
                  <p key={i} className="hint">
                    {f.source}：{f.error}
                  </p>
                ))}
                {e.payload.report && (
                  <div className="report">
                    <p>{e.payload.report.summary}</p>
                    <h4>风险提示</h4>
                    <ul>
                      {e.payload.report.risks.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                    {e.payload.report.suggestions.map((s) => (
                      <div key={s.watch_id} className="report-suggestion">
                        <b>
                          {watches.find((w) => w.id === s.watch_id)?.name ||
                            s.watch_id}
                          <Pill tone={s.delta ? "sand" : ""}>
                            {s.delta
                              ? `${s.delta > 0 ? "加仓" : "减仓"} ${Math.abs(s.delta)} 份`
                              : "继续观察"}
                          </Pill>
                        </b>
                        {s.reasons.map((r, i) => (
                          <p key={i}>{r}</p>
                        ))}
                        <small>失效条件：{s.invalidation}</small>
                      </div>
                    ))}
                  </div>
                )}
                {delivery?.error && (
                  <p className="hint">
                    发送 {delivery.attempts} 次 · {delivery.error}
                  </p>
                )}
                <details>
                  <summary>查看记录与依据</summary>
                  <pre>{JSON.stringify(e.payload, null, 2)}</pre>
                </details>
              </section>
            );
          })}
        {!events.length && (
          <section className="card">
            <Empty
              title="每一次提醒，都有依据"
              text="开盘观察、阈值事件、AI 分析与持仓修改记录会保存在这里。"
            />
          </section>
        )}
      </section>
    </>
  );
}

function SettingsPage({
  notify,
  reload,
}: {
  notify: (s: string) => void;
  reload: () => Promise<void>;
}) {
  const [s, setS] = useState<Settings | null>(null),
    [loadError, setLoadError] = useState(""),
    [loadAttempt, setLoadAttempt] = useState(0),
    [busy, setBusy] = useState(false),
    [feedName, setFeedName] = useState(""),
    [feedUrl, setFeedUrl] = useState(""),
    [keywords, setKeywords] = useState("");
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    setLoadError("");
    api<Settings>("/settings", "GET", undefined, { signal: controller.signal })
      .then((v) => {
        if (cancelled) return;
        setS(v);
        setKeywords(v.keywords.join("，"));
      })
      .catch((e) => {
        if (!cancelled) setLoadError(e.message);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [loadAttempt]);
  const change = (key: keyof Settings, value: unknown) =>
    setS((old) => (old ? { ...old, [key]: value } : old));
  async function save() {
    if (!s) return;
    setBusy(true);
    try {
      const body = Object.fromEntries(
        Object.entries({
          ...s,
          keywords: keywords
            .split(/[,，\n]/)
            .map((x) => x.trim())
            .filter(Boolean),
        }).filter(([k]) => !k.endsWith("_configured")),
      );
      const r = await api<Settings>("/settings", "PUT", body);
      setS(r);
      notify("偏好设置已保存");
      await reload();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function test(path: string) {
    setBusy(true);
    try {
      await api(path, "POST");
      notify("连接测试成功");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!s)
    return loadError ? (
      <section className="card connection-failure" role="alert">
        <CircleHelp size={28} />
        <h2>偏好设置加载失败</h2>
        <p>{loadError}</p>
        <button
          className="primary"
          onClick={() => setLoadAttempt((n) => n + 1)}
        >
          重新加载设置
        </button>
        <p className="muted">不会覆盖你已保存的配置。</p>
      </section>
    ) : (
      <div className="loading">
        <Loader2 className="spin" />
        正在加载设置…
      </div>
    );
  return (
    <div className="settings-layout">
      <div>
        <section className="card settings-card">
          <div className="card-heading">
            <div>
              <h2>
                <ShieldCheck size={19} />
                分析偏好
              </h2>
              <small>行情、程序策略和 AI 分别控制</small>
            </div>
          </div>
          <Switch
            title="启用程序策略建议"
            text="基于完整日线技术指标与持仓限制，给出份额提示"
            value={s.strategy_enabled}
            onChange={(v) => change("strategy_enabled", v)}
          />
          <Switch
            title="启用 AI 辅助分析"
            text="仅分析功能调用 AI；开启后，日报可附加 AI 分析"
            value={s.ai_enabled}
            onChange={(v) => change("ai_enabled", v)}
          />
          <div className="form-grid">
            <label>
              兼容 API 地址
              <input
                value={s.ai_base_url}
                onChange={(e) => change("ai_base_url", e.target.value)}
                placeholder="https://api.openai.com/v1"
              />
            </label>
            <label>
              模型名称
              <input
                value={s.ai_model}
                onChange={(e) => change("ai_model", e.target.value)}
                placeholder="填写服务商提供的模型 ID"
              />
            </label>
            <label>
              API Key
              <input
                type="password"
                autoComplete="new-password"
                value={s.ai_key ?? ""}
                onChange={(e) => change("ai_key", e.target.value)}
                placeholder={
                  s.ai_key_configured ? "已配置，留空保留；输入替换" : "未配置"
                }
              />
              {s.ai_key_configured && (
                <button
                  type="button"
                  className="text-link danger"
                  onClick={() => change("ai_key", "")}
                >
                  清除密钥（保存生效）
                </button>
              )}
            </label>
            <label>
              接口格式
              <select
                value={s.ai_interface}
                onChange={(e) => change("ai_interface", e.target.value)}
              >
                <option value="chat">Chat Completions</option>
                <option value="responses">Responses</option>
              </select>
            </label>
            <label>
              每日调用上限（UTC 日）
              <input
                type="number"
                min="1"
                max="100"
                value={s.ai_daily_limit}
                onChange={(e) =>
                  change("ai_daily_limit", Number(e.target.value))
                }
              />
            </label>
          </div>
          <div className="privacy-note">
            <LockKeyhole size={15} />
            <p>
              向所配置的服务发送行情、新闻标题、持仓比例与约束；不发送资金金额。连接测试也计入每日调用次数。请先保存再测试。
            </p>
          </div>
          <button
            className="secondary"
            disabled={busy || !s.ai_enabled}
            onClick={() => void test("/ai/test")}
          >
            <Sparkles size={15} />
            测试 AI 连接
          </button>
        </section>
        <section className="card settings-card">
          <div className="card-heading">
            <div>
              <h2>
                <Bell size={19} />
                推送与交易日
              </h2>
              <small>股票按交易日；加密现货全天监控，按 UTC 日期去重</small>
            </div>
          </div>
          <Switch
            title="每日行情观察推送"
            text="股票开盘后 30 分钟；加密货币每天北京时间 08:30。错过 15 分钟窗口不补发过时建议"
            value={s.notify_daily}
            onChange={(v) => change("notify_daily", v)}
          />
          <Switch
            title="盘中异常提醒"
            text="达到涨跌阈值时推送，同方向同档位每日去重；加密货币相对上一 UTC 日收盘计算"
            value={s.notify_alerts}
            onChange={(v) => change("notify_alerts", v)}
          />
          <label className="field-label">监控市场</label>
          <div className="checkbox-row">
            {(["CN", "HK", "US", "CRYPTO"] as Market[]).map((m) => (
              <label key={m}>
                <input
                  type="checkbox"
                  checked={s.markets.includes(m)}
                  onChange={(e) =>
                    change(
                      "markets",
                      e.target.checked
                        ? [...s.markets, m]
                        : s.markets.filter((x) => x !== m),
                    )
                  }
                />
                {marketName[m]}
              </label>
            ))}
          </div>
          <div className="form-grid">
            <label>
              静默开始（北京时间）
              <input
                type="time"
                value={s.quiet_start}
                onChange={(e) => change("quiet_start", e.target.value)}
              />
            </label>
            <label>
              静默结束（北京时间）
              <input
                type="time"
                value={s.quiet_end}
                onChange={(e) => change("quiet_end", e.target.value)}
              />
            </label>
            <label className="full">
              Webhook 地址
              <input
                value={s.webhook_url}
                onChange={(e) => change("webhook_url", e.target.value)}
                placeholder="https://your-service.example/webhook"
              />
            </label>
            <label>
              签名密钥（可选）
              <input
                type="password"
                value={s.webhook_secret ?? ""}
                onChange={(e) => change("webhook_secret", e.target.value)}
                placeholder={
                  s.webhook_secret_configured
                    ? "已配置，未修改则保留"
                    : "HMAC-SHA256 签名"
                }
              />
            </label>
            <label>
              Authorization 请求头（可选）
              <input
                type="password"
                value={s.webhook_authorization ?? ""}
                onChange={(e) =>
                  change("webhook_authorization", e.target.value)
                }
                placeholder={
                  s.webhook_authorization_configured
                    ? "已配置，未修改则保留"
                    : "例如 Bearer ..."
                }
              />
            </label>
          </div>
          <p className="muted">
            通用 JSON
            Webhook，接收端需适配该格式。静默期间不发送，过期提醒丢弃；测试消息立即发送。
          </p>
          <button
            className="secondary"
            disabled={busy || !s.webhook_url}
            onClick={() => void test("/webhook/test")}
          >
            测试推送连接 <ArrowRight size={15} />
          </button>
        </section>
        <section className="card settings-card">
          <div className="card-heading">
            <h2>
              <BookOpen size={19} />
              资讯来源与订阅
            </h2>
          </div>
          <label>
            关注方向与关键词
            <textarea
              rows={3}
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="纳斯达克，红利，半导体，利率"
            />
            <small>中英文逗号或换行分隔；按标题匹配，不调用 AI。</small>
          </label>
          <SourcePanel
            enabledNews={s.news_sources || []}
            onNewsChange={(ids) => change("news_sources", ids)}
            quotes
          />
          <div className="feed-list">
            {s.feeds.map((f, i) => (
              <div key={i}>
                <div>
                  <b>{f.name}</b>
                  <small>{f.url}</small>
                </div>
                <button
                  className="icon-btn danger"
                  aria-label="删除资讯源"
                  onClick={() =>
                    change(
                      "feeds",
                      s.feeds.filter((_, n) => n !== i),
                    )
                  }
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
          <div className="form-grid">
            <label>
              来源名称
              <input
                value={feedName}
                onChange={(e) => setFeedName(e.target.value)}
                placeholder="你信任的财经源"
              />
            </label>
            <label>
              RSS / Atom 地址
              <input
                value={feedUrl}
                onChange={(e) => setFeedUrl(e.target.value)}
                placeholder="https://.../rss.xml"
              />
            </label>
          </div>
          <button
            className="secondary"
            disabled={!feedName || !feedUrl}
            onClick={() => {
              change("feeds", [...s.feeds, { name: feedName, url: feedUrl }]);
              setFeedName("");
              setFeedUrl("");
            }}
          >
            <Plus size={15} />
            添加来源（保存生效）
          </button>
        </section>
        <section className="card settings-card">
          <div className="card-heading">
            <h2>
              <Globe2 size={19} />
              行情数据源
            </h2>
          </div>
          <label>
            数据提供方式
            <select
              value={s.provider}
              onChange={(e) => change("provider", e.target.value)}
            >
              <option value="auto">
                自动切换 · 腾讯 / 东方财富 / Yahoo 主备
              </option>
              <option value="tencent">腾讯财经 · 独立报价，备用图表</option>
              <option value="eastmoney">东方财富 · A 股</option>
              <option value="yahoo">Yahoo Finance · 实验性非官方接口</option>
              <option value="custom">自定义标准化行情接口</option>
            </select>
          </label>
          {s.provider !== "custom" ? (
            <p className="hint">
              此接口没有稳定性和实时性承诺，可能被限流。仅用于个人验证；长期使用请接入获授权的数据源。无有效数据时不生成操作建议。
            </p>
          ) : (
            <div className="form-grid">
              <label>
                标准接口地址
                <input
                  value={s.provider_base_url}
                  onChange={(e) => change("provider_base_url", e.target.value)}
                  placeholder="https://your-provider.example/api"
                />
              </label>
              <label>
                接口密钥
                <input
                  type="password"
                  value={s.provider_key ?? ""}
                  onChange={(e) => change("provider_key", e.target.value)}
                  placeholder={
                    s.provider_key_configured
                      ? "已配置，未修改则保留"
                      : "可选 Bearer 密钥"
                  }
                />
              </label>
            </div>
          )}
          <p className="muted">
            自定义接口需实现 /search 和 /quote，字段协议见项目
            docs/DATA_SOURCES.md。仅支持场内股票和 ETF。
          </p>
        </section>
      </div>
      <aside className="settings-aside">
        <div className="card">
          <div className="summary-icon mint">
            <Settings2 size={21} />
          </div>
          <h3>按照你的节奏</h3>
          <p>
            先保存配置，再测试连接。程序与 AI 都不会直接修改持仓或发起交易。
          </p>
          <button
            className="primary"
            disabled={busy}
            onClick={() => void save()}
          >
            {busy ? (
              <Loader2 size={16} className="spin" />
            ) : (
              <Check size={16} />
            )}
            保存全部设置
          </button>
          <small>敏感配置在后端加密保存。</small>
        </div>
        <div className="aside-tip">
          <CircleHelp size={18} />
          <p>
            美股通常在北京时间晚间交易。如果设置夜间静默，可能收不到该时段的日报和风险提醒。
          </p>
        </div>
      </aside>
    </div>
  );
}
function Switch({
  title,
  text,
  value,
  onChange,
}: {
  title: string;
  text: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="switch-row">
      <div>
        <b>{title}</b>
        <p>{text}</p>
      </div>
      <button
        type="button"
        className={"switch " + (value ? "on" : "")}
        role="switch"
        aria-checked={value}
        aria-label={title}
        onClick={() => onChange(!value)}
      >
        <span />
      </button>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
