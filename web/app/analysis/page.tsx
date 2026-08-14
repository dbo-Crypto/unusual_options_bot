"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Stat } from "@/components/Stat";
import { api } from "@/lib/api";
import { money, tone } from "@/lib/format";
import type { AnalysisBucket, AnalysisReport, GrokReview } from "@/lib/types";

export default function AnalysisPage() {
  const [report, setReport] = useState<AnalysisReport>();
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [paste, setPaste] = useState("");

  async function load() {
    setReport(await api.analysis());
  }

  useEffect(() => {
    load().catch((e) => setMsg(String(e)));
  }, []);

  async function runGrok() {
    setBusy(true);
    try {
      const grok = await api.grokAnalysis();
      setReport((cur) => (cur ? { ...cur, grok: grok as GrokReview } : cur));
      setMsg("Grok re-read the book.");
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runNow() {
    const out = await api.autoRun();
    setMsg(`Auto-trader bought ${out.bought?.length || 0}, sold ${out.sold?.length || 0}, skipped ${out.skipped?.length || 0}.`);
    await load();
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl tracking-tight">Analysis</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">
            Grok reads every paper fill and every scored alert, then says what to change. Numbers first, then the review.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={btn()} onClick={() => void runNow()}>
            Run auto-trader now
          </button>
        </div>
      </div>
      {msg ? <p className="text-sm text-zinc-400">{msg}</p> : null}

      <section className="hairline rounded-2xl bg-ink-850/80 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-medium tracking-tight text-zinc-200">Grok desk review</h2>
            <p className="mt-1 text-sm text-zinc-500">
              Download the briefing and upload it in Grok chat (X Premium), or ask Grok here if an API key is set.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => {
                setDownloading(true);
                api
                  .downloadBriefing()
                  .catch((e) => setMsg(String(e)))
                  .finally(() => setDownloading(false));
              }}
              className={btn()}
            >
              {downloading ? "Preparing…" : "Download for Grok chat"}
            </button>
            <a href="https://grok.x.com" target="_blank" rel="noreferrer" className={btn()}>
              Open grok.x.com
            </a>
            <button type="button" onClick={() => void runGrok()} disabled={busy} className={btn()}>
              {busy ? "Reading the book…" : "Ask Grok"}
            </button>
          </div>
        </div>
        <label className="mt-4 block text-xs uppercase tracking-wider text-zinc-500">
          Paste Grok&apos;s reply
          <textarea
            value={paste}
            onChange={(e) => setPaste(e.target.value)}
            rows={5}
            placeholder="Paste the full Grok answer here…"
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-400/40"
          />
        </label>
        <button
          className={`${btn()} mt-2`}
          onClick={async () => {
            if (!paste.trim()) return;
            const grok = await api.importGrok(paste);
            setPaste("");
            setReport((cur) => (cur ? { ...cur, grok: grok as GrokReview } : cur));
            setMsg("Imported Grok's X Premium review.");
          }}
        >
          Save reply on this page
        </button>
        {report?.grok ? (
          <div className="mt-5 space-y-4">
            <div className="text-[11px] uppercase tracking-wider text-zinc-500">
              {report.grok.source || "local"}
              {report.grok.generated_at ? ` · ${report.grok.generated_at.slice(0, 16).replace("T", " ")} UTC` : ""}
            </div>
            <div className="text-lg text-zinc-100">{report.grok.headline}</div>
            <p className="text-sm leading-relaxed text-zinc-300">{report.grok.summary}</p>
            {report.grok.note ? <p className="text-sm text-amber-200">{report.grok.note}</p> : null}
            <List title="What the book shows" items={report.grok.findings || []} />
            <List title="What to change" items={report.grok.changes || []} />
            <List title="Do not fool yourself" items={report.grok.risks || []} />
          </div>
        ) : null}
      </section>

      {!report ? (
        <p className="text-zinc-500">Loading analysis…</p>
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            <Stat label="Trades" value={String(report.overall.n)} hint={`${report.open_count} still open`} />
            <Stat
              label="Win rate"
              value={`${report.overall.win_rate}%`}
              hint={`${report.overall.winners}W / ${report.overall.losers}L`}
            />
            <Stat label="Net P&L" value={money(report.overall.total_pnl)} signed raw={report.overall.total_pnl} />
            <Stat label="Expectancy" value={money(report.overall.expectancy)} signed raw={report.overall.expectancy} hint="per trade" />
          </div>
          <section className="hairline rounded-2xl bg-ink-850/80 p-5">
            <h2 className="text-base font-medium tracking-tight text-zinc-200">Rule notes</h2>
            <ul className="mt-3 space-y-2">
              {report.lessons.map((note) => (
                <li key={note} className="text-sm leading-relaxed text-zinc-300">
                  {note}
                </li>
              ))}
            </ul>
          </section>
          <div className="grid gap-4 lg:grid-cols-2">
            <BucketTable title="Stock vs option" rows={report.by_kind} />
            <BucketTable title="Calls vs puts" rows={report.by_side} />
            <BucketTable title="By unusual score" rows={report.by_score} />
            <BucketTable title="Auto vs manual" rows={report.by_origin} />
          </div>
          <BucketTable title="By detector tag" rows={report.by_tag} />
          <section className="hairline overflow-hidden rounded-2xl bg-ink-850/80">
            <div className="border-b border-white/5 px-4 py-3 text-base font-medium tracking-tight text-zinc-200">
              Every paper trade
            </div>
            <table className="w-full text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wider text-zinc-500">
                <tr>
                  {["Name", "Kind", "How", "Score", "P&L", "Result"].map((col) => (
                    <th key={col} className="px-4 py-2 font-medium">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.trades.map((t) => (
                  <tr key={t.id} className="border-t border-white/5">
                    <td className="px-4 py-2">
                      <Link href={`/ticker/${t.symbol}`} className="hover:text-white">
                        {t.symbol}
                      </Link>{" "}
                      <span className="text-zinc-500">{t.company_name}</span>
                    </td>
                    <td className="px-4 py-2 capitalize text-zinc-400">{t.kind}</td>
                    <td className="px-4 py-2 text-zinc-400">{t.origin}</td>
                    <td className="px-4 py-2 font-mono">{t.score ?? "—"}</td>
                    <td className={`px-4 py-2 font-mono ${tone(t.pnl)}`}>{money(t.pnl)}</td>
                    <td className={`px-4 py-2 capitalize ${tone(t.pnl)}`}>{t.result}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <h3 className="text-sm text-zinc-200">{title}</h3>
      <ul className="mt-2 space-y-2">
        {items.map((item) => (
          <li key={item} className="text-sm leading-relaxed text-zinc-300">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function BucketTable({ title, rows }: { title: string; rows: Record<string, AnalysisBucket> }) {
  const keys = Object.keys(rows);
  return (
    <section className="hairline overflow-hidden rounded-2xl bg-ink-850/80">
      <div className="border-b border-white/5 px-4 py-3 text-sm text-zinc-300">{title}</div>
      {!keys.length ? (
        <p className="px-4 py-4 text-sm text-zinc-500">No trades in this slice yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-[11px] uppercase tracking-wider text-zinc-500">
            <tr>
              {["Bucket", "N", "Win", "P&L"].map((col) => (
                <th key={col} className="px-4 py-2 font-medium">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => {
              const b = rows[k];
              return (
                <tr key={k} className="border-t border-white/5">
                  <td className="px-4 py-2">{k}</td>
                  <td className="px-4 py-2 font-mono">{b.n}</td>
                  <td className="px-4 py-2 font-mono">{b.win_rate}%</td>
                  <td className={`px-4 py-2 font-mono ${tone(b.total_pnl)}`}>{money(b.total_pnl)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

function btn() {
  return "rounded-full border border-white/10 px-4 py-2 text-sm text-zinc-200 hover:border-white/25 disabled:opacity-40";
}
