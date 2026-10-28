export type Market = "CN" | "HK" | "US";
export type Bar = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};
export type Quote = {
  price?: number;
  previous_close?: number;
  change_pct?: number;
  currency?: string;
  as_of?: string;
  source?: string;
  delay_note?: string;
  intraday?: Bar[];
  history?: Bar[];
};
export type Signal = {
  watch_id: string;
  name: string;
  symbol: string;
  action: string;
  action_label: string;
  delta: number;
  held: number;
  reasons: string[];
  constraints: string[];
  metrics: Record<string, number | string | boolean | null> | null;
  quote_at?: string;
  rule_version: string;
};
export type Watch = {
  id: string;
  symbol: string;
  name: string;
  market: Market;
  exchange: string;
  kind: string;
  threshold: number;
  quote: Quote;
  live: boolean;
  error?: string;
  signal: Signal;
};
export type Position = {
  watch_id: string;
  shares: number | string;
  target: number | string | null;
  cap: number | string;
};
export type Portfolio = {
  revision: number;
  positions: Position[];
  cash: number | string;
  min_cash: number | string;
  max_step: number | string;
  risk: string;
  horizon: string;
  updated_at: string;
};
export type MarketState = {
  market: Market;
  name: string;
  status: string;
  is_open: boolean;
  date: string;
  daily_at?: string;
  error?: string;
};
export type Report = {
  summary: string;
  risks: string[];
  suggestions: {
    watch_id: string;
    action: string;
    delta: number;
    reasons: string[];
    sources: string[];
    invalidation: string;
  }[];
};
export type Event = {
  id: string;
  created: string;
  kind: string;
  title: string;
  payload: {
    status?: string;
    error?: string;
    report?: Report;
    summary?: string;
    failures?: { source: string; error: string }[];
    [key: string]: unknown;
  };
};
export type Dashboard = {
  watchlist: Watch[];
  markets: MarketState[];
  portfolio: Portfolio;
  events: Event[];
  worker_heartbeat?: string;
  mode: { ai: boolean; strategy: boolean };
  keywords: string[];
};
export type News = {
  id: string;
  title: string;
  url: string;
  source: string;
  published: string;
  tags: string[];
};
export type Settings = {
  ai_enabled: boolean;
  strategy_enabled: boolean;
  ai_base_url: string;
  ai_model: string;
  ai_interface: string;
  ai_daily_limit: number;
  ai_key?: string;
  ai_key_configured?: boolean;
  webhook_url: string;
  webhook_secret?: string;
  webhook_secret_configured?: boolean;
  webhook_authorization?: string;
  webhook_authorization_configured?: boolean;
  notify_daily: boolean;
  notify_alerts: boolean;
  markets: Market[];
  quiet_start: string;
  quiet_end: string;
  keywords: string[];
  feeds: { name: string; url: string }[];
  provider: string;
  provider_base_url: string;
  provider_key?: string;
  provider_key_configured?: boolean;
};
