export function money(value: number, digits = 2): string {
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toFixed(digits)}`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function clsx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function tone(value: number): string {
  if (value > 0.0001) return "text-emerald-400";
  if (value < -0.0001) return "text-rose-400";
  return "text-zinc-400";
}

export function num(n: number | null | undefined, d = 0) {
  return n == null || Number.isNaN(n) ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: d });
}

export function fmtExpiry(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = iso.slice(0, 10);
  return d.slice(5).replace("-", "/");
}

export function compactMoney(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
}
