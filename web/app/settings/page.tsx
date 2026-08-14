"use client";

import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { fetchHealth, fetchWatchlist, putWatchlist } from "@/lib/api";
import type { Health } from "@/lib/types";

export default function SettingsPage() {
  const [health, setHealth] = useState<Health>();
  const [watch, setWatch] = useState("NVDA, AMD, AVGO, SMH, AAPL, TSLA, PLTR");
  const [saved, setSaved] = useState("");

  useEffect(() => {
    Promise.all([fetchHealth().catch(() => undefined), fetchWatchlist().catch(() => ({ symbols: [] }))]).then(
      ([h, w]) => {
        setHealth(h);
        if (w.symbols.length) setWatch(w.symbols.join(", "));
      }
    );
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const symbols = watch
      .split(/[\s,]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    await putWatchlist(symbols);
    setSaved(`Saved ${symbols.length} symbols. Live mode deep-scans these every cycle.`);
  }

  const ingest = health?.state?.ingest?.value;

  return (
    <Shell health={health}>
      <h1 className="text-2xl font-medium tracking-tight">Health & settings</h1>
      <p className="mt-1 mb-6 max-w-2xl text-sm text-mist-500">
        No API keys. Replay mode uses checked-in fixtures. Live mode polls delayed Yahoo chains and official OCC open
        interest. Switch with <code className="font-mono text-amber">DATA_MODE=live</code> in Compose.
      </p>

      <div className="mb-6 rounded-lg border border-ink-700 bg-ink-900 p-4 text-sm text-mist-300">
        <h2 className="text-xs uppercase tracking-wide text-mist-500">How often the bot runs</h2>
        <p className="mt-2">{health?.cadence || "Worker has not reported a cadence yet."}</p>
        <ul className="mt-3 list-disc space-y-1 pl-4">
          <li>
            Right now you are in <span className="font-mono text-amber">{health?.mode || "…"}</span> mode.
          </li>
          <li>
            Live poll interval:{" "}
            <span className="font-mono">{health?.poll_interval_seconds ?? 240}s</span> (
            {Math.round((health?.poll_interval_seconds ?? 240) / 60)} minutes), set by{" "}
            <code className="font-mono text-amber">POLL_INTERVAL_SECONDS</code>.
          </li>
          <li>
            Live name cap: <span className="font-mono">{health?.max_scan_underlyings ?? 120}</span> underlyings per
            cycle (<code className="font-mono text-amber">MAX_SCAN_UNDERLYINGS</code>).
          </li>
        </ul>
        <p className="mt-3">
          Yahoo is unofficial and has no public quota. A full live cycle can be hundreds of chain requests. You{" "}
          <strong>can</strong> get blocked if you run live at 120 names every 4 minutes all day. Replay mode (the
          default) hits no Yahoo/OCC APIs. If you switch to live, start with a small watchlist and 5–10 minute polls.
        </p>
      </div>

      <div className="mb-8 grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-ink-700 bg-ink-900 p-4">
          <h2 className="text-xs uppercase tracking-wide text-mist-500">Ingest</h2>
          <pre className="mt-2 overflow-auto font-mono text-xs text-mist-300">
            {JSON.stringify(ingest || { waiting: "worker has not reported yet" }, null, 2)}
          </pre>
        </div>
        <div className="rounded-lg border border-ink-700 bg-ink-900 p-4 text-sm text-mist-300">
          <h2 className="text-xs uppercase tracking-wide text-mist-500">What this is not</h2>
          <ul className="mt-2 list-disc space-y-1 pl-4">
            <li>Not Unusual Whales live flow. Sweeps and aggressor side need a paid OPRA tape.</li>
            <li>Not a real brokerage. Paper trades never hit the market.</li>
            <li>Yahoo is unofficial and delayed ~15 minutes. It can rate-limit.</li>
            <li>OI you see during the session is yesterday&apos;s official OI.</li>
          </ul>
        </div>
      </div>

      <form onSubmit={save} className="max-w-xl rounded-lg border border-ink-700 bg-ink-900 p-4">
        <label className="text-xs uppercase text-mist-500">
          Watchlist
          <textarea
            value={watch}
            onChange={(e) => setWatch(e.target.value)}
            rows={4}
            className="mt-1 w-full rounded-md border border-ink-600 bg-ink-800 px-2 py-1.5 font-mono text-sm text-mist-100"
          />
        </label>
        <button className="mt-3 rounded-md bg-mist-100 px-3 py-1.5 text-sm text-ink-950">Save watchlist</button>
        {saved && <p className="mt-2 text-xs text-call">{saved}</p>}
      </form>
    </Shell>
  );
}
