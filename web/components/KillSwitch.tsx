"use client";

import { api } from "@/lib/api";

export function KillSwitch({ killed, state }: { killed: boolean; state: string }) {
  async function toggle() {
    await api.control(killed || state === "paused" ? "start" : "kill");
    window.location.reload();
  }

  return (
    <button
      onClick={() => void toggle()}
      className={`group relative flex items-center gap-3 rounded-full border px-4 py-2 text-sm transition ${
        killed
          ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
          : "border-white/10 bg-white/[0.03] text-zinc-200 hover:border-rose-400/40"
      }`}
    >
      <span
        className={`h-2.5 w-2.5 rounded-full ${killed ? "bg-rose-400 shadow-[0_0_12px_#ff5d73]" : "bg-emerald-400 shadow-[0_0_12px_#3ee08f]"}`}
      />
      <span className="font-medium tracking-wide">{killed ? "HALTED — resume" : "KILL SWITCH"}</span>
    </button>
  );
}
