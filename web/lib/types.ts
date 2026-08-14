export type Signal = {
  id: string;
  created_at: string;
  occ_symbol: string;
  underlying: string;
  company_name?: string | null;
  expiry: string;
  strike: number;
  call_put: "C" | "P";
  score: number;
  direction: string;
  status: "live" | "confirmed" | "faded" | "hedge";
  reasons: { code: string; text: string }[];
  tags: string[];
  volume: number | null;
  open_interest: number | null;
  vol_oi: number | null;
  est_premium: number | null;
  iv: number | null;
  iv_delta: number | null;
  spot: number | null;
  last_price?: number | null;
  source: string;
  data_asof: string | null;
  session_date: string | null;
  plain_english?: string | null;
  actionable?: boolean | null;
  suggested_action?: string | null;
  outcome_verdict?: string | null;
  outcome_quality?: string | null;
  outcome_return_pct?: number | null;
  outcome_spot?: number | null;
  outcome_plain?: string | null;
  outcome_news?: { title: string; published_at?: string; url?: string; source?: string }[] | null;
};

export type PaperPosition = {
  id: string;
  kind: "stock" | "option";
  symbol: string;
  company_name: string | null;
  occ_symbol: string | null;
  expiry: string | null;
  strike: number | null;
  call_put: string | null;
  qty: number;
  entry_price: number;
  entry_spot: number | null;
  mark_price: number | null;
  mark_spot: number | null;
  opened_at: string;
  closed_at: string | null;
  close_price: number | null;
  realized_pnl: number | null;
  result: string | null;
  status: "open" | "closed" | "expired";
  thesis: string | null;
  origin?: string | null;
  score?: number | null;
  tags?: string[];
  close_reason?: string | null;
};

export type PaperAccount = {
  cash: number;
  starting_cash: number;
  equity: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl: number;
  open_count: number;
  winners: number;
  losers: number;
  flat: number;
  worker_state?: string;
  killed?: boolean;
  last_error?: string | null;
  positions: PaperPosition[];
};

export type Overview = {
  account: PaperAccount;
  health: Health;
  settings: Record<string, string | number | boolean>;
  stats: {
    wins: number;
    losses: number;
    flats: number;
    win_rate: number | null;
    signals: number;
  };
};

export type GrokReview = {
  source?: string;
  note?: string;
  generated_at?: string;
  headline?: string;
  summary?: string;
  findings?: string[];
  changes?: string[];
  risks?: string[];
  sample?: Record<string, unknown>;
};

export type AnalysisBucket = {
  n: number;
  winners: number;
  losers: number;
  flat: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  total_pnl: number;
  expectancy: number;
  profit_factor: number | null;
};

export type AnalysisReport = {
  overall: AnalysisBucket;
  open_count: number;
  closed_count: number;
  by_kind: Record<string, AnalysisBucket>;
  by_side: Record<string, AnalysisBucket>;
  by_origin: Record<string, AnalysisBucket>;
  by_score: Record<string, AnalysisBucket>;
  by_tag: Record<string, AnalysisBucket>;
  lessons: string[];
  grok?: GrokReview | null;
  trades: Array<{
    id: string;
    symbol: string;
    company_name: string | null;
    kind: string;
    origin: string;
    score: number | null;
    tags: string[];
    pnl: number;
    status: string;
    result: string;
  }>;
};

export type Health = {
  ok: boolean;
  mode: string;
  signals: number;
  last_signal_at: string | null;
  disclaimer: string;
  poll_interval_seconds?: number;
  max_scan_underlyings?: number;
  cadence?: string;
  state: Record<string, { value: Record<string, unknown>; updated_at: string }>;
};

export type TickerPayload = {
  underlying: {
    symbol: string;
    name: string | null;
    sector: string | null;
    next_earnings: string | null;
    last_spot: number | null;
    last_spot_change_pct: number | null;
  };
  net: { call_premium: number; put_premium: number; put_call: number | null };
  chain: Array<{
    occ_symbol: string;
    expiry: string;
    strike: number;
    call_put: string;
    volume: number | null;
    open_interest: number | null;
    last_price: number | null;
    bid: number | null;
    ask: number | null;
    iv: number | null;
    est_premium: number | null;
    time: string;
  }>;
  signals: Signal[];
  confirmation: Signal[];
};

export type AlertRule = {
  id: string;
  name: string;
  enabled: boolean;
  min_score: number;
  filters: Record<string, unknown>;
  channels: { type: string; url?: string }[];
  cooldown_seconds: number;
  digest_seconds: number;
};
