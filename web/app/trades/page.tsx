"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Stat } from "@/components/Stat";
import { api } from "@/lib/api";
import { money, tone } from "@/lib/format";
import type { PaperAccount, PaperPosition } from "@/lib/types";

export default function TradesPage() {
  const [acct, setAcct] = useState<PaperAccount>();
  const [err, setErr] = useState("");

  async function load() {
    setAcct(await api.paper());
  }

  useEffect(() => {
    load().catch((e) => setErr(String(e)));
  }, []);

  const open = acct?.positions.filter((p) => p.status === "open") || [];
  const closed = acct?.positions.filter((p) => p.status !== "open") || [];
  const paperPnl = acct?.unrealized_pnl ?? 0;
  const lockedPnl = acct?.realized_pnl ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl tracking-tight">Trades</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-500">
          Fully automatic paper book. The bot buys calls, puts, and leftover stock when flow is clean, and sells on
          take-profit, stop-loss, dead thesis, or opposite flow.
        </p>
      </div>
      {err ? <p className="text-sm text-rose-300">{err}</p> : null}
      {acct ? (
        <div className="grid gap-3 md:grid-cols-4">
          <Stat label="Cash" value={money(acct.cash)} hint="what you can still spend" />
          <Stat label="Equity" value={money(acct.equity)} hint="cash + open marks" />
          <Stat label="Paper P&L" value={money(paperPnl)} signed raw={paperPnl} hint={`${open.length} open`} />
          <Stat label="Locked P&L" value={money(lockedPnl)} signed raw={lockedPnl} hint={`${closed.length} closed`} />
        </div>
      ) : null}

      <h2 className="text-sm uppercase tracking-[0.2em] text-zinc-500">Open — paper P&L only</h2>
      {!open.length ? (
        <p className="text-sm text-zinc-500">
          Nothing open. Wait for the next scan, or open{" "}
          <Link href="/analysis" className="text-zinc-300 underline">
            Analysis
          </Link>{" "}
          and run the auto-trader.
        </p>
      ) : (
        <Table rows={open} pnlLabel="Paper P&L" />
      )}

      <h2 className="text-sm uppercase tracking-[0.2em] text-zinc-500">Closed — locked P&L</h2>
      {!closed.length ? (
        <p className="text-sm text-zinc-500">
          No locked trades yet. The bot locks P&L when a take-profit, stop-loss, expired option, or dead thesis fires.
        </p>
      ) : (
        <Table rows={closed} pnlLabel="Locked P&L" />
      )}
    </div>
  );
}

function Table({ rows, pnlLabel }: { rows: PaperPosition[]; pnlLabel: string }) {
  return (
    <div className="hairline overflow-hidden rounded-2xl bg-ink-850/80">
      <table className="w-full text-left text-sm">
        <thead className="text-[11px] uppercase tracking-wider text-zinc-500">
          <tr>
            <th className="px-4 py-2 font-medium">What</th>
            <th className="px-4 py-2 font-medium text-right">Qty</th>
            <th className="px-4 py-2 font-medium text-right">Entry</th>
            <th className="px-4 py-2 font-medium text-right">Now / exit</th>
            <th className="px-4 py-2 font-medium text-right">{pnlLabel}</th>
            <th className="px-4 py-2 font-medium">Result / why</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => {
            const mult = p.kind === "option" ? 100 : 1;
            const mark = p.status === "open" ? p.mark_price : p.close_price;
            const pnl =
              p.status === "open"
                ? p.qty * ((p.mark_price ?? p.entry_price) - p.entry_price) * mult
                : p.realized_pnl || 0;
            const result = p.result || (pnl > 0.5 ? "winner" : pnl < -0.5 ? "loser" : "flat");
            return (
              <tr key={p.id} className="border-t border-white/5 align-top">
                <td className="px-4 py-2">
                  <div className="font-medium">
                    {p.symbol} <span className="font-normal text-zinc-500">{p.company_name}</span>
                  </div>
                  <div className="font-mono text-[11px] text-zinc-500">
                    {p.kind === "option"
                      ? `${p.expiry?.slice(0, 10)} $${p.strike}${p.call_put} · option`
                      : "shares of stock"}
                    {p.origin === "auto" ? " · auto" : ""}
                  </div>
                </td>
                <td className="px-4 py-2 text-right font-mono">{p.qty}</td>
                <td className="px-4 py-2 text-right font-mono">${p.entry_price.toFixed(2)}</td>
                <td className="px-4 py-2 text-right font-mono">{mark != null ? `$${mark.toFixed(2)}` : "—"}</td>
                <td className={`px-4 py-2 text-right font-mono ${tone(pnl)}`}>{money(pnl)}</td>
                <td className={`px-4 py-2 ${tone(pnl)}`}>
                  {p.status === "open" ? (
                    "not locked"
                  ) : (
                    <span>
                      <span className="capitalize">{result}</span>
                      {p.close_reason ? (
                        <div className="mt-0.5 text-[11px] font-normal text-zinc-500">{p.close_reason}</div>
                      ) : null}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
