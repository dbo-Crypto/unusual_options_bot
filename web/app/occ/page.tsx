"use client";

import { useEffect, useState } from "react";
import { FeedTable } from "@/components/FeedTable";
import { api } from "@/lib/api";
import type { Signal } from "@/lib/types";

export default function OccPage() {
  const [sessionDate, setSessionDate] = useState<string | null>(null);
  const [items, setItems] = useState<Signal[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const report = await api.occ();
        if (!alive) return;
        setSessionDate(report.session_date);
        setItems(report.items);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "failed");
      }
    }
    void load();
    const id = setInterval(() => void load(), 20000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const groups = {
    confirmed: items.filter((s) => s.status === "confirmed"),
    faded: items.filter((s) => s.status === "faded"),
    hedge: items.filter((s) => s.status === "hedge"),
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl tracking-tight">OCC confirmation</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-500">
          Official open interest updates once a day. This is the filter that turns yesterday&apos;s volume spike into
          someone actually opening a position — or throws it out.
          {sessionDate ? ` Session ${sessionDate}.` : ""}
        </p>
      </div>
      {error ? <p className="text-sm text-zinc-500">{error}</p> : null}
      {(["confirmed", "faded", "hedge"] as const).map((k) => (
        <section key={k}>
          <h2 className="mb-3 text-sm uppercase tracking-[0.2em] text-zinc-500">
            {k} · {groups[k].length}
          </h2>
          <FeedTable items={groups[k]} />
        </section>
      ))}
    </div>
  );
}
