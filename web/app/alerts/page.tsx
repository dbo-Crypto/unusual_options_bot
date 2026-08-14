"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AlertRule } from "@/lib/types";

export default function AlertsPage() {
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [name, setName] = useState("Watchlist high conviction");
  const [min, setMin] = useState(80);
  const [webhook, setWebhook] = useState("");
  const [msg, setMsg] = useState("");

  async function refresh() {
    setRules((await api.rules()).items);
  }

  useEffect(() => {
    refresh().catch((e) => setMsg(String(e)));
  }, []);

  async function addRule(e: React.FormEvent) {
    e.preventDefault();
    await api.createRule({
      name,
      enabled: true,
      min_score: min,
      filters: { exclude_tags: ["0dte", "roll", "two_sided"] },
      channels: webhook ? [{ type: webhook.includes("discord") ? "discord" : "webhook", url: webhook }] : [],
      cooldown_seconds: 1800,
      digest_seconds: 900,
    });
    setMsg("Rule saved. Discord/webhook fires when the worker scores a matching contract.");
    setWebhook("");
    await refresh();
  }

  async function toggle(rule: AlertRule) {
    await api.updateRule(rule.id, { ...rule, enabled: !rule.enabled });
    await refresh();
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl tracking-tight">Alerts</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Rules run after every scoring pass. Default filters drop 0DTE, rolls, and two-sided vol trades. Leave the
          webhook empty for in-app only.
        </p>
      </div>
      {msg ? <p className="text-sm text-zinc-400">{msg}</p> : null}
      <form onSubmit={addRule} className="hairline space-y-3 rounded-2xl bg-ink-850/80 p-5">
        <label className="block text-xs uppercase tracking-wider text-zinc-500">
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-emerald-400/40"
          />
        </label>
        <label className="block text-xs uppercase tracking-wider text-zinc-500">
          Min score
          <input
            type="number"
            value={min}
            onChange={(e) => setMin(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm outline-none focus:border-emerald-400/40"
          />
        </label>
        <label className="block text-xs uppercase tracking-wider text-zinc-500">
          Discord or webhook URL
          <input
            value={webhook}
            onChange={(e) => setWebhook(e.target.value)}
            placeholder="https://discord.com/api/webhooks/…"
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-emerald-400/40"
          />
        </label>
        <button className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-200">
          Save rule
        </button>
      </form>
      <div className="space-y-3">
        {rules.map((rule) => (
          <div key={rule.id} className="hairline flex items-center justify-between rounded-2xl bg-ink-850/80 px-4 py-3">
            <div>
              <div className="text-sm">{rule.name}</div>
              <div className="font-mono text-[11px] text-zinc-500">min {rule.min_score}</div>
            </div>
            <button
              onClick={() => void toggle(rule)}
              className={`rounded-full border px-3 py-1 text-[11px] uppercase tracking-wider ${
                rule.enabled ? "border-emerald-400/30 text-emerald-300" : "border-white/10 text-zinc-500"
              }`}
            >
              {rule.enabled ? "on" : "off"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
