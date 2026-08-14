"use client";

import { useEffect, useState } from "react";
import { useDesk } from "@/components/useDesk";
import { api } from "@/lib/api";

const FIELDS: { key: string; label: string; hint: string; step?: string }[] = [
  { key: "poll_interval_seconds", label: "Loop", hint: "Live Yahoo/OCC cycle, seconds. Restart worker to apply.", step: "30" },
  { key: "max_scan_underlyings", label: "Scan cap", hint: "Underlyings deep-scanned per cycle", step: "1" },
  { key: "feed_min_score", label: "Feed min score", hint: "Default filter on Overview", step: "1" },
  { key: "auto_min_score", label: "Auto-trade min score", hint: "Only buy alerts at or above this", step: "1" },
  { key: "option_take_profit", label: "Option take-profit", hint: "Close the option at this gain", step: "0.05" },
  { key: "option_stop_loss", label: "Option stop", hint: "Close the option at this loss", step: "0.05" },
  { key: "stock_take_profit", label: "Stock take-profit", hint: "Close leftover shares at this gain", step: "0.01" },
  { key: "stock_stop_loss", label: "Stock stop", hint: "Close leftover shares at this loss", step: "0.01" },
];

export default function ControlPage() {
  const { data, refresh } = useDesk();
  const [form, setForm] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (data?.settings) {
      const next: Record<string, string> = {};
      for (const [k, v] of Object.entries(data.settings)) next[k] = String(v);
      setForm(next);
    }
  }, [data]);

  async function save() {
    const body: Record<string, string | number | boolean> = {};
    for (const field of FIELDS) {
      if (form[field.key] != null && form[field.key] !== "") body[field.key] = Number(form[field.key]);
    }
    if (form.watchlist != null) body.watchlist = form.watchlist;
    if (form.auto_enabled != null) body.auto_enabled = form.auto_enabled === "true";
    await api.patchSettings(body);
    setStatus("Saved. Auto-trade knobs apply on the next cycle.");
    await refresh();
  }

  async function act(action: string) {
    await api.control(action);
    setStatus(`Issued ${action}.`);
    await refresh();
  }

  const ingest = data?.health.state?.ingest?.value;

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl tracking-tight">Control</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Paper only. These knobs never place a live broker order. Reset drops open trades and restores virtual $1,000.
          Closed (locked) history is kept.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button className={btn()} onClick={() => void act("start")}>
          Start
        </button>
        <button className={btn()} onClick={() => void act("pause")}>
          Pause
        </button>
        <button className={btn("border-rose-500/40 text-rose-300")} onClick={() => void act("kill")}>
          Kill
        </button>
        <button className={btn("border-amber-500/40 text-amber-200")} onClick={() => void act("reset")}>
          Reset bankroll
        </button>
      </div>

      <div className="hairline rounded-2xl bg-ink-850/80 p-5 text-sm text-zinc-400">
        <div className="text-[11px] uppercase tracking-wider text-zinc-500">Mode</div>
        <p className="mt-2">{data?.health.cadence || "Worker has not reported a cadence yet."}</p>
        <p className="mt-2">
          Right now: <span className="font-mono text-amber-200">{data?.health.mode || "…"}</span>
          {ingest?.delay ? ` · ${String(ingest.delay)}` : ""}
        </p>
      </div>

      <div className="hairline space-y-4 rounded-2xl bg-ink-850/80 p-5">
        <label className="flex items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={form.auto_enabled !== "false"}
            onChange={(e) => setForm({ ...form, auto_enabled: String(e.target.checked) })}
          />
          Auto-trader on
        </label>
        {FIELDS.map((field) => (
          <label key={field.key} className="grid grid-cols-[14rem_1fr] items-center gap-4">
            <span>
              <span className="block text-sm">{field.label}</span>
              <span className="block text-xs text-zinc-500">{field.hint}</span>
            </span>
            <input
              className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm outline-none focus:border-emerald-400/40"
              type="number"
              step={field.step}
              value={form[field.key] ?? ""}
              onChange={(event) => setForm({ ...form, [field.key]: event.target.value })}
            />
          </label>
        ))}
        <label className="grid grid-cols-[14rem_1fr] items-start gap-4">
          <span>
            <span className="block text-sm">Watchlist</span>
            <span className="block text-xs text-zinc-500">Always deep-scanned each live cycle</span>
          </span>
          <textarea
            className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm outline-none focus:border-emerald-400/40"
            rows={3}
            value={form.watchlist ?? ""}
            onChange={(event) => setForm({ ...form, watchlist: event.target.value })}
          />
        </label>
        <button className={btn("border-emerald-400/30 bg-emerald-400/10 text-emerald-200")} onClick={() => void save()}>
          Save settings
        </button>
        {status ? <div className="text-sm text-zinc-400">{status}</div> : null}
      </div>
    </div>
  );
}

function btn(extra = "") {
  return `rounded-full border border-white/10 px-4 py-2 text-sm hover:bg-white/5 ${extra}`;
}
