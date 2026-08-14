import { FeedTable } from "@/components/FeedTable";
import { Shell } from "@/components/Shell";
import { fetchHealth, fetchScreeners, fetchSignals } from "@/lib/api";

export const dynamic = "force-dynamic";

type Props = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function Home({ searchParams }: Props) {
  const sp = await searchParams;
  const preset = typeof sp.preset === "string" ? sp.preset : "";
  const min = typeof sp.min === "string" ? sp.min : "70";
  const cp = typeof sp.cp === "string" ? sp.cp : "";
  const status = typeof sp.status === "string" ? sp.status : "live";

  const [health, screeners, data] = await Promise.all([
    fetchHealth().catch(() => undefined),
    fetchScreeners().catch(() => ({ items: [] })),
    fetchSignals({
      min_score: min,
      call_put: cp || undefined,
      status: status || undefined,
    }).catch(() => ({ items: [], count: 0 })),
  ]);

  let items = data.items;
  const selected = screeners.items.find((s) => s.id === preset);
  if (selected) {
    const f = selected.filters || {};
    items = items.filter((s) => {
      if (f.call_put && s.call_put !== f.call_put) return false;
      if (typeof f.min_score === "number" && s.score < f.min_score) return false;
      if (typeof f.min_vol_oi === "number" && (s.vol_oi || 0) < f.min_vol_oi) return false;
      const tags = new Set(s.tags || []);
      if (Array.isArray(f.tags) && !f.tags.every((t) => tags.has(String(t)))) return false;
      if (Array.isArray(f.exclude_tags) && f.exclude_tags.some((t) => tags.has(String(t)))) return false;
      return true;
    });
  }

  return (
    <Shell health={health}>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-medium tracking-tight">Unusual activity</h1>
          <p className="mt-1 max-w-2xl text-sm text-mist-500">
            Contract snapshots, not a live print tape. Ranked by an explainable 0–100 score against each name&apos;s own
            baseline. Premium is estimated.
          </p>
        </div>
        <form className="flex flex-wrap items-center gap-2 text-sm">
          <select name="preset" defaultValue={preset} className="rounded-md border border-ink-600 bg-ink-800 px-2 py-1.5">
            <option value="">All unusual</option>
            {screeners.items.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <select name="min" defaultValue={min} className="rounded-md border border-ink-600 bg-ink-800 px-2 py-1.5">
            <option value="55">Score ≥ 55</option>
            <option value="70">Score ≥ 70</option>
            <option value="80">Score ≥ 80</option>
          </select>
          <select name="cp" defaultValue={cp} className="rounded-md border border-ink-600 bg-ink-800 px-2 py-1.5">
            <option value="">Calls + puts</option>
            <option value="C">Calls</option>
            <option value="P">Puts</option>
          </select>
          <select name="status" defaultValue={status} className="rounded-md border border-ink-600 bg-ink-800 px-2 py-1.5">
            <option value="live">Live</option>
            <option value="">All statuses</option>
            <option value="confirmed">Confirmed</option>
            <option value="faded">Faded</option>
            <option value="hedge">Hedge</option>
          </select>
          <button className="rounded-md bg-mist-100 px-3 py-1.5 text-ink-950">Apply</button>
        </form>
      </div>
      <FeedTable items={items} />
    </Shell>
  );
}
