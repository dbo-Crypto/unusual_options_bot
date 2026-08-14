"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { FeedTable } from "@/components/FeedTable";
import { api } from "@/lib/api";
import { compactMoney, num, tone } from "@/lib/format";
import type { TickerPayload } from "@/lib/types";

export default function TickerPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = String(params.symbol || "").toUpperCase();
  const [data, setData] = useState<TickerPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol) return;
    api
      .ticker(symbol)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "not found"));
  }, [symbol]);

  if (error) {
    return (
      <div className="hairline rounded-2xl p-10 text-center">
        <div className="text-lg">Ticker unavailable</div>
        <div className="mt-2 text-sm text-zinc-500">{error}</div>
      </div>
    );
  }
  if (!data) return <p className="text-zinc-500">Loading {symbol}…</p>;

  const u = data.underlying;
  const chg = u.last_spot_change_pct;
  const chain = [...data.chain].sort((a, b) => (b.est_premium || 0) - (a.est_premium || 0)).slice(0, 16);

  return (
    <div className="space-y-8">
      <Link href="/" className="text-xs text-zinc-500 hover:text-zinc-300">
        ← Overview
      </Link>
      <div className="flex flex-wrap items-end gap-6">
        <div>
          <h1 className="text-3xl tracking-tight">{u.symbol}</h1>
          <p className="text-sm text-zinc-500">
            {u.name} · {u.sector || "—"}
            {u.next_earnings ? ` · earnings ${u.next_earnings}` : ""}
          </p>
        </div>
        <div className="font-mono">
          <div className="text-2xl">{u.last_spot?.toFixed(2) ?? "—"}</div>
          <div className={chg != null ? tone(chg) : "text-zinc-500"}>
            {chg == null ? "—" : `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`}
          </div>
        </div>
        <div className="text-sm text-zinc-500">
          <div>
            Est. call prem <span className="font-mono text-emerald-400">{compactMoney(data.net.call_premium)}</span>
          </div>
          <div>
            Est. put prem <span className="font-mono text-rose-400">{compactMoney(data.net.put_premium)}</span>
          </div>
        </div>
      </div>

      <section>
        <h2 className="mb-3 text-sm uppercase tracking-[0.2em] text-zinc-500">Live unusual</h2>
        <FeedTable items={data.signals} />
      </section>
      <section>
        <h2 className="mb-3 text-sm uppercase tracking-[0.2em] text-zinc-500">OCC confirmation</h2>
        {data.confirmation.length ? (
          <FeedTable items={data.confirmation} />
        ) : (
          <p className="text-sm text-zinc-500">No next-day official OI verdict yet for this name.</p>
        )}
      </section>
      <section className="hairline overflow-hidden rounded-2xl bg-ink-850/80">
        <div className="border-b border-white/5 px-4 py-3 text-sm text-zinc-300">Chain snapshot (top premium)</div>
        <table className="w-full text-left text-sm">
          <thead className="text-[11px] uppercase tracking-wider text-zinc-500">
            <tr>
              <th className="px-4 py-2 font-medium">Contract</th>
              <th className="px-4 py-2 font-medium text-right">Vol</th>
              <th className="px-4 py-2 font-medium text-right">OI</th>
              <th className="px-4 py-2 font-medium text-right">Last</th>
              <th className="px-4 py-2 font-medium text-right">IV</th>
              <th className="px-4 py-2 font-medium text-right">Est. prem</th>
            </tr>
          </thead>
          <tbody>
            {chain.map((c) => (
              <tr key={c.occ_symbol} className="border-t border-white/5">
                <td className={`px-4 py-2 font-mono text-xs ${c.call_put === "C" ? "text-emerald-400" : "text-rose-400"}`}>
                  {c.expiry?.slice(5)} {c.strike}
                  {c.call_put}
                </td>
                <td className="px-4 py-2 text-right font-mono text-xs">{num(c.volume)}</td>
                <td className="px-4 py-2 text-right font-mono text-xs">{num(c.open_interest)}</td>
                <td className="px-4 py-2 text-right font-mono text-xs">{c.last_price?.toFixed(2) ?? "—"}</td>
                <td className="px-4 py-2 text-right font-mono text-xs">
                  {c.iv != null ? `${(c.iv * 100).toFixed(1)}%` : "—"}
                </td>
                <td className="px-4 py-2 text-right font-mono text-xs">{compactMoney(c.est_premium)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
