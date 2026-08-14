"use client";

import Link from "next/link";
import type { Signal } from "@/lib/types";
import { fmtExpiry, money, num } from "@/lib/api";

function Score({ n }: { n: number }) {
  const color = n >= 80 ? "text-amber" : n >= 70 ? "text-call" : "text-mist-300";
  return <span className={`font-mono text-lg font-semibold ${color}`}>{n.toFixed(0)}</span>;
}

function Tag({ t }: { t: string }) {
  const hot = ["multi_day", "vol_oi_extreme", "sector", "size", "confirmed"].includes(t);
  const warn = ["earnings", "0dte", "lottery", "two_sided", "roll", "possible_hedge", "hedge"].includes(t);
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase ${
        hot ? "bg-call/10 text-call" : warn ? "bg-put/10 text-put" : "bg-ink-700 text-mist-500"
      }`}
    >
      {t}
    </span>
  );
}

function sideLabel(s: Signal) {
  if (s.call_put === "C") return "Call — pays if the stock goes up";
  return "Put — pays if the stock goes down (or is used as insurance)";
}

function qualityLabel(q?: string | null) {
  switch (q) {
    case "good_signal":
      return { label: "Would have been a good directional hint", cls: "border-call/40 text-call" };
    case "poor_signal":
      return { label: "Poor signal this time — stock went the other way", cls: "border-put/40 text-put" };
    case "not_a_trade":
      return { label: "Not a buy/sell signal (hedge or noise)", cls: "border-amber/40 text-amber" };
    case "too_soon":
      return { label: "Too soon to judge — waiting for a later price", cls: "border-ink-600 text-mist-500" };
    default:
      return { label: "Mixed / no follow-through yet", cls: "border-ink-600 text-mist-300" };
  }
}

function OutcomeBox({ signal: s }: { signal: Signal }) {
  const q = qualityLabel(s.outcome_quality);
  const news = s.outcome_news || [];
  return (
    <div className={`mt-3 rounded-md border px-3 py-2 ${q.cls}`}>
      <div className="text-[11px] font-medium uppercase tracking-wide">{q.label}</div>
      {s.outcome_return_pct != null && (
        <div className="mt-0.5 font-mono text-xs">
          Stock after the alert: {s.outcome_spot != null ? `$${s.outcome_spot.toFixed(2)}` : "—"} (
          {s.outcome_return_pct >= 0 ? "+" : ""}
          {(s.outcome_return_pct * 100).toFixed(1)}%)
        </div>
      )}
      <p className="mt-1 text-sm leading-relaxed text-mist-300">{s.outcome_plain || "Outcome not scored yet."}</p>
      {news.length > 0 && (
        <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs text-mist-500">
          {news.slice(0, 3).map((n) => (
            <li key={n.title}>
              {n.url ? (
                <a href={n.url} className="text-ice underline" target="_blank" rel="noreferrer">
                  {n.title}
                </a>
              ) : (
                n.title
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function FeedTable({ items }: { items: Signal[] }) {
  if (!items.length) {
    return (
      <div className="rounded-lg border border-ink-700 bg-ink-900 px-6 py-16 text-center text-mist-500">
        No contracts match these filters. In live mode this fills after the first Yahoo poll.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {items.map((s) => (
        <article key={s.id} className="rounded-lg border border-ink-700 bg-ink-900 p-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-[220px]">
              <div className="flex items-baseline gap-2">
                <Link href={`/ticker/${s.underlying}`} className="text-lg font-medium hover:text-ice">
                  {s.underlying}
                </Link>
                <span className="text-sm text-mist-300">{s.company_name || s.underlying}</span>
              </div>
              <div className={`mt-0.5 font-mono text-xs ${s.call_put === "C" ? "text-call" : "text-put"}`}>
                {fmtExpiry(s.expiry)} ${s.strike}
                {s.call_put} · {sideLabel(s)}
              </div>
              <div className="mt-1 text-[11px] uppercase tracking-wide text-mist-500">
                {s.direction} · {s.status}
                {s.spot != null ? ` · stock $${s.spot.toFixed(2)}` : ""}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-wide text-mist-500">Unusual score</div>
              <Score n={s.score} />
            </div>
          </div>

          <p className="mt-3 max-w-4xl text-sm leading-relaxed text-mist-300">
            {s.plain_english || (s.reasons || []).map((r) => r.text).join(" ")}
          </p>

          <OutcomeBox signal={s} />

          <div className="mt-3">
            <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-mist-500">
              <span>Vol {num(s.volume)}</span>
              <span>Open interest {num(s.open_interest)}</span>
              <span>Vol/OI {s.vol_oi?.toFixed(1) ?? "—"}</span>
              <span>Est. money {money(s.est_premium)}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {(s.tags || []).slice(0, 8).map((t) => (
                <Tag key={t} t={t} />
              ))}
            </div>
            {s.actionable !== false && s.score >= 80 && (
              <p className="mt-2 text-[11px] text-mist-500">
                Auto-trader will buy this {s.call_put === "C" ? "call" : "put"}
                {s.call_put === "C" ? " (and leftover stock on the strongest name)" : ""} if cash remains.
              </p>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
