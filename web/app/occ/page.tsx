import { FeedTable } from "@/components/FeedTable";
import { Shell } from "@/components/Shell";
import { fetchHealth, fetchOccReport } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function OccPage() {
  const [health, report] = await Promise.all([
    fetchHealth().catch(() => undefined),
    fetchOccReport().catch(() => ({ session_date: null, items: [] })),
  ]);
  const groups = {
    confirmed: report.items.filter((s) => s.status === "confirmed"),
    faded: report.items.filter((s) => s.status === "faded"),
    hedge: report.items.filter((s) => s.status === "hedge"),
  };
  return (
    <Shell health={health}>
      <h1 className="text-2xl font-medium tracking-tight">Overnight OCC confirmation</h1>
      <p className="mt-1 mb-6 max-w-2xl text-sm text-mist-500">
        Official open interest updates once a day. This is the filter that turns yesterday&apos;s volume spike into
        &quot;someone actually opened a position&quot; — or throws it out.
        {report.session_date ? ` Session ${report.session_date}.` : ""}
      </p>
      {(["confirmed", "faded", "hedge"] as const).map((k) => (
        <section key={k} className="mb-8">
          <h2 className="mb-2 text-sm uppercase tracking-wide text-mist-500">
            {k} · {groups[k].length}
          </h2>
          <FeedTable items={groups[k]} />
        </section>
      ))}
    </Shell>
  );
}
