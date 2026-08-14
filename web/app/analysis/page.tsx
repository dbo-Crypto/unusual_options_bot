"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Shell } from "@/components/Shell";
import {
  API,
  fetchAnalysis,
  fetchAutoSettings,
  fetchHealth,
  importGrokPaste,
  money,
  runAutoTrader,
  runGrokReview,
  saveAutoSettings,
} from "@/lib/api";
import type { AnalysisBucket, AnalysisReport, Health } from "@/lib/types";

function pnlClass(n: number) {
  if (n > 0.5) return "text-call";
  if (n < -0.5) return "text-put";
  return "text-mist-500";
}

export default function AnalysisPage() {
  const [health, setHealth] = useState<Health>();
  const [report, setReport] = useState<AnalysisReport>();
  const [auto, setAuto] = useState({
    enabled: true,
    min_score: 80,
    option_take_profit: 0.3,
    option_stop_loss: 0.4,
    stock_take_profit: 0.05,
    stock_stop_loss: 0.04,
  });
  const [msg, setMsg] = useState("");
  const [grokBusy, setGrokBusy] = useState(false);
  const [paste, setPaste] = useState("");

  async function load() {
    const [h, r, a] = await Promise.all([
      fetchHealth().catch(() => undefined),
      fetchAnalysis(),
      fetchAutoSettings().catch(() => auto),
    ]);
    setHealth(h);
    setReport(r);
    setAuto(a);
  }

  useEffect(() => {
    load().catch((e) => setMsg(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    await saveAutoSettings(auto);
    setMsg("Auto-trader settings saved. They apply on the next scan.");
  }

  async function runNow() {
    const out = await runAutoTrader();
    setMsg(
      `Auto-trader bought ${out.bought?.length || 0}, sold ${out.sold?.length || 0}, skipped ${out.skipped?.length || 0}.`
    );
    await load();
  }

  return (
    <Shell health={health}>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium tracking-tight">Strategy analysis</h1>
          <p className="mt-1 max-w-2xl text-sm text-mist-500">
            Grok reads every paper fill and every scored alert, then says what to change. Numbers first, then the
            review.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={async () => {
              setGrokBusy(true);
              try {
                await runGrokReview();
                await load();
                setMsg("Grok re-read the book.");
              } catch (e) {
                setMsg(String(e));
              } finally {
                setGrokBusy(false);
              }
            }}
            className="rounded-md bg-mist-100 px-3 py-1.5 text-sm text-ink-950"
          >
            {grokBusy ? "Reading…" : "Ask Grok to re-read"}
          </button>
          <button onClick={runNow} className="rounded-md border border-ink-600 px-3 py-1.5 text-sm text-mist-300">
            Run auto-trader now
          </button>
        </div>
      </div>

      {msg && <p className="mb-4 text-sm text-call">{msg}</p>}

      <section className="mb-8 rounded-lg border border-ink-700 bg-ink-900 p-4">
        <h2 className="text-sm uppercase tracking-wide text-mist-500">Use Grok on X Premium (no API key)</h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-mist-300">
          X Premium is chat, not an API. Download a <span className="font-mono">.txt</span> of the full book, upload
          that file in{" "}
          <a href="https://grok.x.com" className="text-ice underline" target="_blank" rel="noreferrer">
            grok.x.com
          </a>
          , then paste Grok&apos;s reply below so it stays on this page.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <a
            href={`${API}/paper/analysis/briefing.txt`}
            className="rounded-md bg-mist-100 px-3 py-1.5 text-sm text-ink-950"
          >
            Download briefing .txt
          </a>
          <a
            href="https://grok.x.com"
            target="_blank"
            rel="noreferrer"
            className="rounded-md border border-ink-600 px-3 py-1.5 text-sm text-mist-300"
          >
            Open grok.x.com
          </a>
        </div>
        <label className="mt-4 block text-xs uppercase text-mist-500">
          Paste Grok&apos;s reply
          <textarea
            value={paste}
            onChange={(e) => setPaste(e.target.value)}
            rows={6}
            placeholder="Paste the full Grok answer here…"
            className="mt-1 w-full rounded-md border border-ink-600 bg-ink-800 px-2 py-1.5 text-sm text-mist-100"
          />
        </label>
        <button
          className="mt-2 rounded-md border border-ink-600 px-3 py-1.5 text-sm"
          onClick={async () => {
            if (!paste.trim()) return;
            await importGrokPaste(paste);
            setPaste("");
            await load();
            setMsg("Imported Grok's X Premium review.");
          }}
        >
          Save reply on this page
        </button>
      </section>

      {report?.grok && (
        <section className="mb-8 rounded-lg border border-ice/40 bg-ink-900 p-5">
          <div className="text-[11px] uppercase tracking-wide text-ice">
            Grok review · {report.grok.source || "local"}
            {report.grok.generated_at ? ` · ${report.grok.generated_at.slice(0, 16).replace("T", " ")} UTC` : ""}
          </div>
          <h2 className="mt-2 text-xl font-medium tracking-tight">{report.grok.headline}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-mist-300">{report.grok.summary}</p>
          {report.grok.note && <p className="mt-2 text-xs text-amber">{report.grok.note}</p>}
          {!!report.grok.findings?.length && (
            <>
              <h3 className="mt-5 text-xs uppercase tracking-wide text-mist-500">What the book shows</h3>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-mist-300">
                {report.grok.findings.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </>
          )}
          {!!report.grok.changes?.length && (
            <>
              <h3 className="mt-5 text-xs uppercase tracking-wide text-mist-500">Change the strategy like this</h3>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-mist-100">
                {report.grok.changes.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </>
          )}
          {!!report.grok.risks?.length && (
            <>
              <h3 className="mt-5 text-xs uppercase tracking-wide text-mist-500">Do not fool yourself</h3>
              <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-mist-500">
                {report.grok.risks.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      <section className="mb-8 rounded-lg border border-ink-700 bg-ink-900 p-4">
        <h2 className="text-sm uppercase tracking-wide text-mist-500">Auto-trader</h2>
        <p className="mt-1 mb-3 text-sm text-mist-300">
          Hands-off. High-score calls buy the call (and leftover stock on the strongest name). High-score puts buy the
          put and sell any long stock on that name. Exits are automatic: take-profit, stop-loss, OCC thesis dead, or
          opposite flow. Hedges, 0-day, rolls, and lottery tickets are never traded.
        </p>
        <div className="flex flex-wrap items-end gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={auto.enabled}
              onChange={(e) => setAuto({ ...auto, enabled: e.target.checked })}
            />
            On
          </label>
          <label className="text-xs text-mist-500">
            Min score
            <input
              type="number"
              value={auto.min_score}
              onChange={(e) => setAuto({ ...auto, min_score: Number(e.target.value) })}
              className="mt-1 block w-20 rounded-md border border-ink-600 bg-ink-800 px-2 py-1 font-mono text-sm text-mist-100"
            />
          </label>
          <label className="text-xs text-mist-500">
            Option take-profit
            <input
              type="number"
              step="0.05"
              value={auto.option_take_profit}
              onChange={(e) => setAuto({ ...auto, option_take_profit: Number(e.target.value) })}
              className="mt-1 block w-24 rounded-md border border-ink-600 bg-ink-800 px-2 py-1 font-mono text-sm text-mist-100"
            />
          </label>
          <label className="text-xs text-mist-500">
            Option stop
            <input
              type="number"
              step="0.05"
              value={auto.option_stop_loss}
              onChange={(e) => setAuto({ ...auto, option_stop_loss: Number(e.target.value) })}
              className="mt-1 block w-24 rounded-md border border-ink-600 bg-ink-800 px-2 py-1 font-mono text-sm text-mist-100"
            />
          </label>
          <button onClick={save} className="rounded-md border border-ink-600 px-3 py-1">
            Save
          </button>
        </div>
      </section>

      {!report ? (
        <p className="text-mist-500">Loading…</p>
      ) : (
        <>
          <div className="mb-8 grid gap-3 sm:grid-cols-4">
            <Stat label="Trades" value={String(report.overall.n)} sub={`${report.open_count} still open`} />
            <Stat
              label="Win rate"
              value={`${report.overall.win_rate}%`}
              sub={`${report.overall.winners} win / ${report.overall.losers} loss`}
            />
            <Stat
              label="Total P&L"
              value={money(report.overall.total_pnl)}
              cls={pnlClass(report.overall.total_pnl)}
            />
            <Stat
              label="Avg trade"
              value={money(report.overall.expectancy)}
              cls={pnlClass(report.overall.expectancy)}
              sub="open trades counted at today’s mark"
            />
          </div>

          <h2 className="mb-2 text-sm uppercase tracking-wide text-mist-500">What to change</h2>
          <ul className="mb-8 list-disc space-y-2 pl-5 text-sm leading-relaxed text-mist-300">
            {report.lessons.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>

          <div className="mb-8 grid gap-6 lg:grid-cols-2">
            <BucketTable title="Stock vs option" rows={report.by_kind} />
            <BucketTable title="Calls vs puts" rows={report.by_side} />
            <BucketTable title="By unusual score" rows={report.by_score} />
            <BucketTable title="Auto vs manual" rows={report.by_origin} />
          </div>

          <h2 className="mb-2 text-sm uppercase tracking-wide text-mist-500">By detector tag</h2>
          <p className="mb-3 text-xs text-mist-500">
            A tag is a reason the alert fired (for example “multi_day” means the same contract lit up several sessions).
            If one tag keeps losing, turn that idea down.
          </p>
          <BucketTable title="" rows={report.by_tag} />

          <h2 className="mb-2 mt-8 text-sm uppercase tracking-wide text-mist-500">Every paper trade</h2>
          <div className="overflow-hidden rounded-lg border border-ink-700">
            <table className="w-full text-left text-sm">
              <thead className="bg-ink-850 font-mono text-[11px] uppercase text-mist-500">
                <tr>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Kind</th>
                  <th className="px-3 py-2">How</th>
                  <th className="px-3 py-2 text-right">Score</th>
                  <th className="px-3 py-2 text-right">P&L</th>
                  <th className="px-3 py-2">Result</th>
                </tr>
              </thead>
              <tbody>
                {report.trades.map((t) => (
                  <tr key={t.id} className="border-t border-ink-700 odd:bg-ink-900">
                    <td className="px-3 py-2">
                      <Link href={`/ticker/${t.symbol}`} className="hover:text-ice">
                        {t.symbol}
                      </Link>{" "}
                      <span className="text-mist-500">{t.company_name}</span>
                    </td>
                    <td className="px-3 py-2 capitalize">{t.kind}</td>
                    <td className="px-3 py-2 text-xs">{t.origin}</td>
                    <td className="px-3 py-2 text-right font-mono">{t.score ?? "—"}</td>
                    <td className={`px-3 py-2 text-right font-mono ${pnlClass(t.pnl)}`}>{money(t.pnl)}</td>
                    <td className={`px-3 py-2 capitalize ${pnlClass(t.pnl)}`}>{t.result}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
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

function BucketTable({ title, rows }: { title: string; rows: Record<string, AnalysisBucket> }) {
  const keys = Object.keys(rows);
  if (!keys.length) {
    return (
      <div>
        {title && <h3 className="mb-2 text-sm uppercase tracking-wide text-mist-500">{title}</h3>}
        <p className="text-sm text-mist-500">No trades in this slice yet.</p>
      </div>
    );
  }
  return (
    <div>
      {title && <h3 className="mb-2 text-sm uppercase tracking-wide text-mist-500">{title}</h3>}
      <div className="overflow-hidden rounded-lg border border-ink-700">
        <table className="w-full text-left text-sm">
          <thead className="bg-ink-850 font-mono text-[11px] uppercase text-mist-500">
            <tr>
              <th className="px-3 py-2">Slice</th>
              <th className="px-3 py-2 text-right">N</th>
              <th className="px-3 py-2 text-right">Win %</th>
              <th className="px-3 py-2 text-right">P&L</th>
              <th className="px-3 py-2 text-right">Avg</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => {
              const b = rows[k];
              return (
                <tr key={k} className="border-t border-ink-700 odd:bg-ink-900">
                  <td className="px-3 py-2">{k}</td>
                  <td className="px-3 py-2 text-right font-mono">{b.n}</td>
                  <td className="px-3 py-2 text-right font-mono">{b.win_rate}%</td>
                  <td className={`px-3 py-2 text-right font-mono ${pnlClass(b.total_pnl)}`}>{money(b.total_pnl)}</td>
                  <td className={`px-3 py-2 text-right font-mono ${pnlClass(b.expectancy)}`}>{money(b.expectancy)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
