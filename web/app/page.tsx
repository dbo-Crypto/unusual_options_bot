"use client";

import { useEffect, useMemo, useState } from "react";
import { FeedTable } from "@/components/FeedTable";
import { Stat } from "@/components/Stat";
import { useDesk } from "@/components/useDesk";
import { api } from "@/lib/api";
import { money, pct } from "@/lib/format";
import type { Signal } from "@/lib/types";

export default function OverviewPage() {
  const { data, error } = useDesk();
  const [items, setItems] = useState<Signal[]>([]);
  const [min, setMin] = useState("70");
  const [cp, setCp] = useState("");
  const [status, setStatus] = useState("live");
  const [preset, setPreset] = useState("");
  const [screeners, setScreeners] = useState<{ id: string; name: string; filters: Record<string, unknown> }[]>([]);

  useEffect(() => {
    void api.screeners().then((r) => setScreeners(r.items)).catch(() => undefined);
  }, []);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const next = await api.signals({
          min_score: min,
          call_put: cp || undefined,
          status: status || undefined,
        });
        if (alive) setItems(next.items);
      } catch {
        /* desk banner handles API down */
      }
    }
    void load();
    const id = setInterval(() => void load(), 12000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [min, cp, status]);

  const filtered = useMemo(() => {
    const selected = screeners.find((s) => s.id === preset);
    if (!selected) return items;
    const f = selected.filters || {};
    return items.filter((s) => {
      if (f.call_put && s.call_put !== f.call_put) return false;
      if (typeof f.min_score === "number" && s.score < f.min_score) return false;
      if (typeof f.min_vol_oi === "number" && (s.vol_oi || 0) < f.min_vol_oi) return false;
      const tags = new Set(s.tags || []);
      if (Array.isArray(f.tags) && !f.tags.every((t) => tags.has(String(t)))) return false;
      if (Array.isArray(f.exclude_tags) && f.exclude_tags.some((t) => tags.has(String(t)))) return false;
      return true;
    });
  }, [items, preset, screeners]);

  if (error && !data) {
    return (
      <div className="hairline rounded-2xl p-10 text-center">
        <div className="text-lg">API offline</div>
        <div className="mt-2 text-sm text-zinc-500">{error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-3 md:grid-cols-5">
        <Stat label="Equity" value={money(data?.account.equity ?? 1000)} hint={`${money(data?.account.cash ?? 1000)} cash`} />
        <Stat
          label="Paper P&L"
          value={money(data?.account.unrealized_pnl ?? 0)}
          signed
          raw={data?.account.unrealized_pnl ?? 0}
          hint="open marks"
        />
        <Stat
          label="Locked P&L"
          value={money(data?.account.realized_pnl ?? 0)}
          signed
          raw={data?.account.realized_pnl ?? 0}
        />
        <Stat
          label="Hit rate"
          value={data?.stats.win_rate == null ? "—" : pct(data.stats.win_rate, 0)}
          hint={`${data?.stats.wins ?? 0}W / ${data?.stats.losses ?? 0}L`}
        />
        <Stat label="Signals" value={String(data?.stats.signals ?? items.length)} hint={data?.health.mode ?? "…"} />
      </div>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl tracking-tight">Unusual activity</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">
            Contract snapshots, not a live print tape. Ranked by an explainable 0–100 score against each name&apos;s own
            baseline.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <select
            value={preset}
            onChange={(e) => setPreset(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 outline-none focus:border-emerald-400/40"
          >
            <option value="">All unusual</option>
            {screeners.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <select
            value={min}
            onChange={(e) => setMin(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 outline-none focus:border-emerald-400/40"
          >
            <option value="55">Score ≥ 55</option>
            <option value="70">Score ≥ 70</option>
            <option value="80">Score ≥ 80</option>
          </select>
          <select
            value={cp}
            onChange={(e) => setCp(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 outline-none focus:border-emerald-400/40"
          >
            <option value="">Calls + puts</option>
            <option value="C">Calls</option>
            <option value="P">Puts</option>
          </select>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 outline-none focus:border-emerald-400/40"
          >
            <option value="live">Live</option>
            <option value="">All statuses</option>
            <option value="confirmed">Confirmed</option>
            <option value="faded">Faded</option>
            <option value="hedge">Hedge</option>
          </select>
        </div>
      </div>
      <FeedTable items={filtered} />
    </div>
  );
}
