import { clsx, tone } from "@/lib/format";

export function Stat({
  label,
  value,
  hint,
  signed = false,
  raw = 0,
}: {
  label: string;
  value: string;
  hint?: string;
  signed?: boolean;
  raw?: number;
}) {
  return (
    <div className="hairline rounded-2xl bg-ink-850/80 p-4">
      <div className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">{label}</div>
      <div className={clsx("mt-2 font-mono text-2xl", signed && tone(raw))}>{value}</div>
      {hint ? <div className="mt-1 text-xs text-zinc-500">{hint}</div> : null}
    </div>
  );
}
