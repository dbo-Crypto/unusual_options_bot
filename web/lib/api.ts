import type { AlertRule, AnalysisReport, Health, PaperAccount, Signal, TickerPayload } from "./types";

export const API =
  typeof window === "undefined"
    ? process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

export function fetchSignals(params: Record<string, string | number | undefined> = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") q.set(k, String(v));
  });
  const qs = q.toString();
  return get<{ items: Signal[]; count: number }>(`/signals${qs ? `?${qs}` : ""}`);
}

export const fetchHealth = () => get<Health>("/health");
export const fetchTicker = (symbol: string) => get<TickerPayload>(`/tickers/${symbol}`);
export const fetchOccReport = () => get<{ session_date: string | null; items: Signal[] }>("/occ/report");
export const fetchScreeners = () => get<{ items: { id: string; name: string; filters: Record<string, unknown> }[] }>("/screeners");
export const fetchRules = () => get<{ items: AlertRule[] }>("/alerts/rules");
export const fetchWatchlist = () => get<{ symbols: string[] }>("/watchlist");
export const fetchPaper = () => get<PaperAccount>("/paper");
export const fetchAnalysis = () => get<AnalysisReport>("/paper/analysis");

export async function runGrokReview() {
  const res = await fetch(`${API}/paper/analysis/grok`, { method: "POST" });
  if (!res.ok) throw new Error("Grok review failed");
  return res.json();
}

export const fetchGrokBriefing = () => get<{ prompt: string; grok_url: string; chars: number }>("/paper/analysis/briefing");

export async function importGrokPaste(text: string) {
  const res = await fetch(`${API}/paper/analysis/grok-import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error("Could not import that reply");
  return res.json();
}
export type AutoSettings = {
  enabled: boolean;
  min_score: number;
  option_take_profit: number;
  option_stop_loss: number;
  stock_take_profit: number;
  stock_stop_loss: number;
};

export const fetchAutoSettings = () => get<AutoSettings>("/paper/auto");

export async function saveAutoSettings(body: AutoSettings) {
  const res = await fetch(`${API}/paper/auto`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("save auto settings failed");
  return res.json();
}

export async function runAutoTrader() {
  const res = await fetch(`${API}/paper/auto-run`, { method: "POST" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "auto-run failed");
  return data;
}

export async function paperReset(wipeHistory = false) {
  const res = await fetch(`${API}/paper/reset?wipe_history=${wipeHistory}`, { method: "POST" });
  if (!res.ok) throw new Error("reset failed");
  return res.json();
}

export async function putWatchlist(symbols: string[]) {
  const res = await fetch(`${API}/watchlist`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols }),
  });
  if (!res.ok) throw new Error("watchlist save failed");
}

export async function createRule(body: Partial<AlertRule>) {
  const res = await fetch(`${API}/alerts/rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("rule create failed");
  return res.json();
}

export async function updateRule(id: string, body: Partial<AlertRule>) {
  const res = await fetch(`${API}/alerts/rules/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("rule update failed");
}

export const money = (n: number | null | undefined) => {
  if (n == null || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
};

export const num = (n: number | null | undefined, d = 0) =>
  n == null || Number.isNaN(n) ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: d });

export const fmtExpiry = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const d = iso.slice(0, 10);
  return d.slice(5).replace("-", "/");
};
