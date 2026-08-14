"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Shell } from "@/components/Shell";
import { fetchHealth, fetchPaper, money, paperReset } from "@/lib/api";
import type { Health, PaperAccount, PaperPosition } from "@/lib/types";

function pnlClass(n: number) {
  if (n > 0.5) return "text-call";
  if (n < -0.5) return "text-put";
  return "text-mist-500";
}

function signed(n: number) {
  const body = money(Math.abs(n));
  if (n > 0.5) return `+${body}`;
  if (n < -0.5) return `−${body}`;
  return body;
}

export default function PaperPage() {
  const [health, setHealth] = useState<Health>();
  const [acct, setAcct] = useState<PaperAccount>();
  const [err, setErr] = useState("");

  async function load() {
    const [h, a] = await Promise.all([fetchHealth().catch(() => undefined), fetchPaper()]);
    setHealth(h);
    setAcct(a);
  }

  useEffect(() => {
    load().catch((e) => setErr(String(e)));
  }, []);

  async function reset() {
    if (!confirm("Reset cash to $1,000 and drop open trades? Closed (locked) history is kept.")) return;
    await paperReset();
    await load();
  }

  const open = acct?.positions.filter((p) => p.status === "open") || [];
  const closed = acct?.positions.filter((p) => p.status !== "open") || [];
  const paperPnl = acct?.unrealized_pnl ?? 0;
  const lockedPnl = acct?.realized_pnl ?? 0;
  const ifClosedNow = paperPnl + lockedPnl;

  return (
    <Shell health={health}>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium tracking-tight">Paper trading</h1>
          <p className="mt-1 max-w-2xl text-sm text-mist-500">
            Fully automatic paper book. The bot buys calls, puts, and leftover stock when flow is clean, and sells on
            take-profit, stop-loss, dead thesis, or opposite flow. No manual tickets.
          </p>
        </div>
        <button onClick={reset} className="rounded-md border border-ink-600 px-3 py-1.5 text-sm text-mist-300">
          Reset cash to $1,000
        </button>
      </div>

      {err && <p className="mb-4 text-sm text-put">{err}</p>}

      {acct && (
        <>
          <div className="mb-4 grid gap-3 lg:grid-cols-2">
            <div className="rounded-lg border border-amber/40 bg-ink-900 p-4">
              <div className="text-[11px] uppercase tracking-wide text-amber">Paper P&amp;L — not locked</div>
              <div className={`mt-1 font-mono text-3xl ${pnlClass(paperPnl)}`}>{signed(paperPnl)}</div>
              <p className="mt-2 text-sm leading-relaxed text-mist-300">
                Mark-to-market on <strong>{open.length} open</strong> position{open.length === 1 ? "" : "s"}. This is
                only a quote. If the option dies or you never hit Close, this number can go to zero. It is{" "}
                <em>not</em> money in the account.
              </p>
            </div>
            <div className="rounded-lg border border-call/40 bg-ink-900 p-4">
              <div className="text-[11px] uppercase tracking-wide text-call">Locked P&amp;L — real for this paper book</div>
              <div className={`mt-1 font-mono text-3xl ${pnlClass(lockedPnl)}`}>{signed(lockedPnl)}</div>
              <p className="mt-2 text-sm leading-relaxed text-mist-300">
                Banked from <strong>{closed.length} closed</strong> trade{closed.length === 1 ? "" : "s"} ({acct.winners}{" "}
                win / {acct.losers} loss). Cash was credited or debited. This is the only P&amp;L that counts as
                finished.
              </p>
            </div>
          </div>

          <div className="mb-8 grid gap-3 sm:grid-cols-4">
            <Stat label="Cash" value={money(acct.cash)} sub="what you can still spend" />
            <Stat label="Account value" value={money(acct.equity)} sub="cash + open positions at mark" />
            <Stat
              label="If you closed everything now"
              value={signed(ifClosedNow)}
              cls={pnlClass(ifClosedNow)}
              sub="locked + paper"
            />
            <Stat
              label="Paper vs locked"
              value={signed(paperPnl - lockedPnl)}
              cls="text-mist-300"
              sub={
                paperPnl === lockedPnl
                  ? "they match"
                  : paperPnl > lockedPnl
                    ? "most of the gain is still unlocked"
                    : "locked book is ahead of the open marks"
              }
            />
          </div>
        </>
      )}

      <h2 className="mb-2 text-sm uppercase tracking-wide text-mist-500">Open — paper P&amp;L only</h2>
      {!open.length ? (
        <p className="mb-8 text-sm text-mist-500">
          Nothing open. Wait for the next scan, or open{" "}
          <Link href="/analysis" className="text-ice underline">
            Analysis
          </Link>{" "}
          and click “Run auto-trader now”.
        </p>
      ) : (
        <Table rows={open} pnlLabel="Paper P&L" />
      )}

      <h2 className="mb-2 mt-8 text-sm uppercase tracking-wide text-mist-500">Closed — locked P&amp;L</h2>
      {!closed.length ? (
        <p className="text-sm text-mist-500">
          No locked trades yet. The bot locks P&amp;L when a take-profit, stop-loss, expired option, or dead thesis
          fires.
        </p>
      ) : (
        <Table rows={closed} pnlLabel="Locked P&L" />
      )}
    </Shell>
  );
}

function Stat({ label, value, sub, cls }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 p-3">
      <div className="text-[11px] uppercase tracking-wide text-mist-500">{label}</div>
      <div className={`font-mono text-xl ${cls || ""}`}>{value}</div>
      {sub && <div className="text-xs text-mist-500">{sub}</div>}
    </div>
  );
}

function Table({
  rows,
  pnlLabel,
}: {
  rows: PaperPosition[];
  pnlLabel: string;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-ink-700">
      <table className="w-full text-left text-sm">
        <thead className="bg-ink-850 font-mono text-[11px] uppercase text-mist-500">
          <tr>
            <th className="px-3 py-2">What</th>
            <th className="px-3 py-2 text-right">Qty</th>
            <th className="px-3 py-2 text-right">Entry</th>
            <th className="px-3 py-2 text-right">Now / exit</th>
            <th className="px-3 py-2 text-right">{pnlLabel}</th>
            <th className="px-3 py-2">Result / why</th>
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
              <tr key={p.id} className="border-t border-ink-700 odd:bg-ink-900 align-top">
                <td className="px-3 py-2">
                  <div className="font-medium">
                    {p.symbol} <span className="font-normal text-mist-500">{p.company_name}</span>
                  </div>
                  <div className="font-mono text-[11px] text-mist-500">
                    {p.kind === "option"
                      ? `${p.expiry?.slice(0, 10)} $${p.strike}${p.call_put} · option`
                      : "shares of stock"}
                    {p.origin === "auto" ? " · auto" : ""}
                  </div>
                </td>
                <td className="px-3 py-2 text-right font-mono">{p.qty}</td>
                <td className="px-3 py-2 text-right font-mono">${p.entry_price.toFixed(2)}</td>
                <td className="px-3 py-2 text-right font-mono">{mark != null ? `$${mark.toFixed(2)}` : "—"}</td>
                <td className={`px-3 py-2 text-right font-mono ${pnlClass(pnl)}`}>{signed(pnl)}</td>
                <td className={`px-3 py-2 ${pnlClass(pnl)}`}>
                  {p.status === "open" ? (
                    "not locked"
                  ) : (
                    <span>
                      <span className="capitalize">{result}</span>
                      {p.close_reason ? (
                        <div className="mt-0.5 text-[11px] font-normal text-mist-500">{p.close_reason}</div>
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
