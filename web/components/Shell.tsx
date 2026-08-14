"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Health } from "@/lib/types";

const NAV = [
  { href: "/", label: "Unusual" },
  { href: "/occ", label: "OCC confirm" },
  { href: "/paper", label: "Paper trades" },
  { href: "/analysis", label: "Analysis" },
  { href: "/alerts", label: "Alerts" },
  { href: "/settings", label: "Health" },
];

export function Shell({ health, children }: { health?: Health; children: React.ReactNode }) {
  const path = usePathname();
  const mode = health?.mode || "…";
  const ingest = health?.state?.ingest?.value as { delay?: string; source?: string } | undefined;
  return (
    <div className="min-h-screen bg-ink-950 text-mist-100">
      <header className="sticky top-0 z-20 border-b border-ink-700 bg-ink-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] items-center gap-6 px-5 py-3">
          <Link href="/" className="flex items-center gap-2 font-medium tracking-tight">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-call shadow-[0_0_12px_#3dd68c]" />
            Unusual Options
          </Link>
          <nav className="flex gap-1 text-sm text-mist-500">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={`rounded-md px-3 py-1.5 ${
                  path === n.href ? "bg-ink-800 text-mist-100" : "hover:bg-ink-800 hover:text-mist-300"
                }`}
              >
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 font-mono text-[11px] uppercase tracking-wide text-mist-500">
            <span className="rounded border border-ink-600 px-2 py-0.5 text-amber">{mode}</span>
            <span className="rounded border border-ink-600 px-2 py-0.5">
              {ingest?.delay || (mode === "replay" ? "fixture" : "delayed 15m")}
            </span>
            <span>{health?.signals ?? 0} signals</span>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1440px] px-5 py-5">{children}</main>
      <footer className="mx-auto max-w-[1440px] px-5 pb-8 text-xs leading-relaxed text-mist-500">
        {health?.disclaimer ||
          "Not investment advice. Premium is estimated. Intraday Yahoo data is delayed. Official OI confirms the next morning."}
      </footer>
    </div>
  );
}
