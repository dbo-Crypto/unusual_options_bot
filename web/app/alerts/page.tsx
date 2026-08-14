"use client";

import { useEffect, useState } from "react";
import { Shell } from "@/components/Shell";
import { API, createRule, fetchHealth, fetchRules, updateRule } from "@/lib/api";
import type { AlertRule, Health } from "@/lib/types";

export default function AlertsPage() {
  const [health, setHealth] = useState<Health>();
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [name, setName] = useState("Watchlist high conviction");
  const [min, setMin] = useState(80);
  const [webhook, setWebhook] = useState("");
  const [msg, setMsg] = useState("");

  async function refresh() {
    const [h, r] = await Promise.all([fetchHealth().catch(() => undefined), fetchRules()]);
    setHealth(h);
    setRules(r.items);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function addRule(e: React.FormEvent) {
    e.preventDefault();
    await createRule({
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
    refresh();
  }

  async function toggle(rule: AlertRule) {
    await updateRule(rule.id, { ...rule, enabled: !rule.enabled });
    refresh();
  }

  return (
    <Shell health={health}>
      <h1 className="text-2xl font-medium tracking-tight">Alerts</h1>
      <p className="mt-1 mb-6 max-w-2xl text-sm text-mist-500">
        Rules run after every scoring pass. Default filters drop 0DTE, rolls, and two-sided vol trades. Leave the webhook
        empty for in-app-only (events still log at {API}/alerts/events).
      </p>

      <form onSubmit={addRule} className="mb-8 grid max-w-xl gap-3 rounded-lg border border-ink-700 bg-ink-900 p-4">
        <label className="text-xs uppercase text-mist-500">
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-md border border-ink-600 bg-ink-800 px-2 py-1.5 text-sm text-mist-100"
          />
        </label>
        <label className="text-xs uppercase text-mist-500">
          Min score
          <input
            type="number"
            value={min}
            onChange={(e) => setMin(Number(e.target.value))}
            className="mt-1 w-full rounded-md border border-ink-600 bg-ink-800 px-2 py-1.5 text-sm text-mist-100"
          />
        </label>
        <label className="text-xs uppercase text-mist-500">
          Discord or webhook URL
          <input
            value={webhook}
            onChange={(e) => setWebhook(e.target.value)}
            placeholder="https://discord.com/api/webhooks/…"
            className="mt-1 w-full rounded-md border border-ink-600 bg-ink-800 px-2 py-1.5 text-sm text-mist-100"
          />
        </label>
        <button className="rounded-md bg-mist-100 px-3 py-1.5 text-sm text-ink-950">Save rule</button>
        {msg && <p className="text-xs text-call">{msg}</p>}
      </form>

      <div className="overflow-hidden rounded-lg border border-ink-700">
        <table className="w-full text-left text-sm">
          <thead className="bg-ink-850 font-mono text-[11px] uppercase text-mist-500">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Min</th>
              <th className="px-3 py-2">Channels</th>
              <th className="px-3 py-2">On</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id} className="border-t border-ink-700 odd:bg-ink-900">
                <td className="px-3 py-2">{r.name}</td>
                <td className="px-3 py-2 font-mono">{r.min_score}</td>
                <td className="px-3 py-2 font-mono text-xs">{r.channels?.length ? r.channels.map((c) => c.type).join(", ") : "log only"}</td>
                <td className="px-3 py-2">
                  <button onClick={() => toggle(r)} className="text-ice underline">
                    {r.enabled ? "enabled" : "paused"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
