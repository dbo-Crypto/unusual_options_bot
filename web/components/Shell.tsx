"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bell, LayoutDashboard, ListOrdered, ScanSearch, Settings2, ShieldCheck } from "lucide-react";
import { KillSwitch } from "./KillSwitch";
import { DeskProvider, useDesk } from "./useDesk";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/occ", label: "OCC", icon: ShieldCheck },
  { href: "/trades", label: "Trades", icon: ListOrdered },
  { href: "/analysis", label: "Analysis", icon: ScanSearch },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/control", label: "Control", icon: Settings2 },
];

function navActive(path: string, href: string): boolean {
  if (href === "/") return path === "/" || path.startsWith("/ticker/");
  return path === href || path.startsWith(`${href}/`);
}

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <DeskProvider pollMs={8000}>
      <ShellInner>{children}</ShellInner>
    </DeskProvider>
  );
}

function ShellInner({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { data, live } = useDesk();
  const state = data?.account.worker_state ?? "…";
  const killed = data?.account.killed ?? false;
  const mode = data?.health.mode ?? "…";

  return (
    <div className="min-h-screen grid grid-cols-[240px_1fr]">
      <aside className="border-r border-white/5 bg-ink-900/80 backdrop-blur-md px-5 py-6 flex flex-col">
        <div className="mb-8">
          <div className="text-[11px] tracking-[0.28em] text-zinc-500">OPTIONS</div>
          <div className="text-lg font-medium tracking-tight">Paper Desk</div>
          <div className="mt-1 text-[11px] font-mono text-emerald-400/80">PAPER · $1,000</div>
        </div>
        <nav className="space-y-1">
          {NAV.map((item) => {
            const active = navActive(path, item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                  active ? "bg-white/5 text-white" : "text-zinc-400 hover:text-white hover:bg-white/[0.03]"
                }`}
              >
                <Icon size={16} />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto space-y-3 pt-8">
          <div className="hairline rounded-xl bg-ink-850 p-3">
            <div className="flex items-center justify-between text-[11px] uppercase tracking-wider text-zinc-500">
              <span>Engine</span>
              <span className="flex items-center gap-1.5">
                <Activity size={11} className={live ? "text-emerald-400" : "text-zinc-600"} />
                <span className={live ? "text-emerald-400" : "text-zinc-600"}>{live ? "live" : "poll"}</span>
              </span>
            </div>
            <div className="mt-2 font-mono text-sm capitalize">{killed ? "killed" : state}</div>
            <div className="mt-1 font-mono text-[11px] uppercase text-zinc-500">{mode}</div>
          </div>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-white/5 bg-[#07080b]/75 backdrop-blur-xl px-8 py-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Paper trading terminal</div>
            <div className="text-sm text-zinc-300">Unusual flow · OCC confirm · Auto paper book</div>
          </div>
          <KillSwitch killed={killed} state={state} />
        </header>
        <main className="px-8 py-6">{children}</main>
      </div>
    </div>
  );
}
