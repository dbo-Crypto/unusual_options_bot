import Link from "next/link";
import { notFound } from "next/navigation";
import { FeedTable } from "@/components/FeedTable";
import { Shell } from "@/components/Shell";
import { fetchHealth, fetchTicker, money, num } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TickerPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const [health, data] = await Promise.all([
    fetchHealth().catch(() => undefined),
    fetchTicker(symbol).catch(() => null),
  ]);
  if (!data) notFound();
  const u = data.underlying;
  const chg = u.last_spot_change_pct;
  const chain = [...data.chain].sort((a, b) => (b.est_premium || 0) - (a.est_premium || 0)).slice(0, 16);

  return (
    <Shell health={health}>
      <Link href="/" className="text-xs text-mist-500 hover:text-mist-300">
        ← feed
      </Link>
      <div className="mt-3 flex flex-wrap items-end gap-6">
        <div>
          <h1 className="text-3xl font-medium tracking-tight">{u.symbol}</h1>
          <p className="text-sm text-mist-500">
            {u.name} · {u.sector || "—"}
            {u.next_earnings ? ` · earnings ${u.next_earnings}` : ""}
          </p>
        </div>
        <div className="font-mono">
          <div className="text-2xl">{u.last_spot?.toFixed(2) ?? "—"}</div>
          <div className={chg && chg < 0 ? "text-put" : "text-call"}>
            {chg == null ? "—" : `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`}
          </div>
        </div>
        <div className="text-sm text-mist-500">
          <div>
            Est. call prem <span className="font-mono text-call">{money(data.net.call_premium)}</span>
          </div>
          <div>
            Est. put prem <span className="font-mono text-put">{money(data.net.put_premium)}</span>
          </div>
        </div>
      </div>

      <h2 className="mb-2 mt-8 text-sm uppercase tracking-wide text-mist-500">Live unusual</h2>
      <FeedTable items={data.signals} />

      <h2 className="mb-2 mt-8 text-sm uppercase tracking-wide text-mist-500">OCC confirmation</h2>
      {data.confirmation.length ? (
        <FeedTable items={data.confirmation} />
      ) : (
        <p className="text-sm text-mist-500">No next-day official OI verdict yet for this name.</p>
      )}

      <h2 className="mb-2 mt-8 text-sm uppercase tracking-wide text-mist-500">Chain snapshot (top premium)</h2>
      <div className="overflow-hidden rounded-lg border border-ink-700">
        <table className="w-full text-left text-sm">
          <thead className="bg-ink-850 font-mono text-[11px] uppercase text-mist-500">
            <tr>
              <th className="px-3 py-2">Contract</th>
              <th className="px-3 py-2 text-right">Vol</th>
              <th className="px-3 py-2 text-right">OI</th>
              <th className="px-3 py-2 text-right">Last</th>
              <th className="px-3 py-2 text-right">IV</th>
              <th className="px-3 py-2 text-right">Est. prem</th>
            </tr>
          </thead>
          <tbody>
            {chain.map((c) => (
              <tr key={c.occ_symbol} className="border-t border-ink-700 odd:bg-ink-900">
                <td className={`px-3 py-2 font-mono text-xs ${c.call_put === "C" ? "text-call" : "text-put"}`}>
                  {c.expiry?.slice(5)} {c.strike}
                  {c.call_put}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">{num(c.volume)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{num(c.open_interest)}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{c.last_price?.toFixed(2) ?? "—"}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {c.iv != null ? `${(c.iv * 100).toFixed(1)}%` : "—"}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">{money(c.est_premium)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
