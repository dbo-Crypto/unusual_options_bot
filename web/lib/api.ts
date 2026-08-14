import type { AlertRule, AnalysisReport, Health, Overview, PaperAccount, Signal, TickerPayload } from "./types";

export const API_URL =
  typeof window === "undefined"
    ? process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const DESK_TOKEN = process.env.NEXT_PUBLIC_DESK_TOKEN ?? "";

function withToken(url: string): string {
  if (!DESK_TOKEN) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(DESK_TOKEN)}`;
}

export const WS_URL = withToken(process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(DESK_TOKEN ? { "X-Desk-Token": DESK_TOKEN } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export type AutoSettings = {
  enabled: boolean;
  min_score: number;
  option_take_profit: number;
  option_stop_loss: number;
  stock_take_profit: number;
  stock_stop_loss: number;
};

export const api = {
  overview: () => request<Overview>("/api/overview"),
  health: () => request<Health>("/api/health"),
  signals: (params: Record<string, string | number | undefined> = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") q.set(k, String(v));
    });
    const qs = q.toString();
    return request<{ items: Signal[]; count: number }>(`/api/signals${qs ? `?${qs}` : ""}`);
  },
  ticker: (symbol: string) => request<TickerPayload>(`/api/tickers/${symbol}`),
  occ: () => request<{ session_date: string | null; items: Signal[] }>("/api/occ/report"),
  screeners: () => request<{ items: { id: string; name: string; filters: Record<string, unknown> }[] }>("/api/screeners"),
  rules: () => request<{ items: AlertRule[] }>("/api/alerts/rules"),
  watchlist: () => request<{ symbols: string[] }>("/api/watchlist"),
  paper: () => request<PaperAccount>("/api/paper"),
  analysis: () => request<AnalysisReport>("/api/paper/analysis"),
  settings: () => request<Record<string, string | number | boolean>>("/api/settings"),
  auto: () => request<AutoSettings>("/api/paper/auto"),
  grokAnalysis: () => request<AnalysisReport["grok"]>("/api/paper/analysis/grok", { method: "POST" }),
  importGrok: (text: string) =>
    request<AnalysisReport["grok"]>("/api/paper/analysis/grok-import", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  saveAuto: (body: AutoSettings) =>
    request<AutoSettings>("/api/paper/auto", { method: "PUT", body: JSON.stringify(body) }),
  patchSettings: (body: Record<string, string | number | boolean>) =>
    request<Record<string, string | number | boolean>>("/api/settings", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  control: (action: string) => request<{ ok: boolean; state: string; killed: boolean }>(`/api/control/${action}`, { method: "POST" }),
  autoRun: () => request<{ bought: unknown[]; sold: unknown[]; skipped: unknown[] }>("/api/paper/auto-run", { method: "POST" }),
  paperReset: (wipeHistory = false) =>
    request<PaperAccount>(`/api/paper/reset?wipe_history=${wipeHistory}`, { method: "POST" }),
  putWatchlist: (symbols: string[]) =>
    request<unknown>("/api/watchlist", { method: "PUT", body: JSON.stringify({ symbols }) }),
  createRule: (body: Partial<AlertRule>) =>
    request<AlertRule>("/api/alerts/rules", { method: "POST", body: JSON.stringify(body) }),
  updateRule: (id: string, body: Partial<AlertRule>) =>
    request<unknown>(`/api/alerts/rules/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  downloadBriefing: async () => {
    const response = await fetch(`${API_URL}/api/paper/analysis/briefing.txt`, {
      headers: DESK_TOKEN ? { "X-Desk-Token": DESK_TOKEN } : {},
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const blob = await response.blob();
    const header = response.headers.get("content-disposition") || "";
    const match = /filename="?([^"]+)"?/.exec(header);
    const name = match?.[1] || "options-desk-briefing.txt";
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};
