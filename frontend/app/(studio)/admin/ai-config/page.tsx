"use client";

import { useCallback, useEffect, useState } from "react";
import { AiUsageGuidePanel } from "@/components/features/admin/AiUsageGuidePanel";
import { Button } from "@/components/ui/button";
import { QualityStars } from "@/components/ui/ScreenModelSelector";
import {
  api,
  type AiConfigResponse,
  type AiProviderStatus,
  type AiTier,
  type ProviderUsage,
} from "@/lib/api";

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic (Claude)",
  openai: "OpenAI (GPT)",
  openrouter: "OpenRouter",
  groq: "Groq ⚡",
  gemini: "Google Gemini",
  cerebras: "Cerebras",
  deepseek: "DeepSeek",
  together: "Together AI",
};

const TIER_CARDS: {
  id: AiTier;
  badge: string;
  name: string;
  summary: string;
  details: string[];
}[] = [
  {
    id: "free",
    badge: "🆓",
    name: "Free mode",
    summary: "$0 per project",
    details: [
      "Gemini + OpenRouter + Groq + Cerebras chains",
      "15-model fallback per task",
      "Best for dev and testing",
    ],
  },
  {
    id: "low_cost",
    badge: "💰",
    name: "Low cost mode",
    summary: "~$0.05–0.15 per project",
    details: [
      "DeepSeek V3 primary (~$0.14/1M tokens)",
      "Together 70B Turbo fallback",
      "Free models as backup",
    ],
  },
  {
    id: "premium",
    badge: "💳",
    name: "Premium mode",
    summary: "~$0.50 per project",
    details: [
      "Claude Sonnet 4.5 default",
      "Best quality for client deliverables",
      "OpenAI fallback",
    ],
  },
];

function ProviderCard({
  provider,
  disabled,
  onSave,
}: {
  provider: AiProviderStatus;
  disabled: boolean;
  onSave: (key: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!key.trim()) return;
    setSaving(true);
    try {
      await onSave(key.trim());
      setEditing(false);
      setKey("");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className={`rounded-xl border p-4 ${
        disabled
          ? "border-gray-800 bg-gray-950 opacity-50"
          : "border-gray-700 bg-gray-900"
      }`}
    >
      <div className="flex items-center justify-between">
        <h3 className="font-medium">
          {PROVIDER_LABELS[provider.provider] ?? provider.provider}
        </h3>
        <span
          className={`text-xs ${
            provider.configured ? "text-green-400" : "text-gray-500"
          }`}
        >
          {provider.configured ? "● CONFIGURED" : "○ NOT SET"}
        </span>
      </div>
      {provider.masked_key && !editing ? (
        <p className="mt-2 text-sm text-gray-400">API Key: {provider.masked_key}</p>
      ) : null}
      {!disabled && (
        <div className="mt-3 flex gap-2">
          {editing ? (
            <>
              <input
                type="password"
                placeholder="sk-..."
                value={key}
                onChange={(e) => setKey(e.target.value)}
                className="flex-1 rounded-md border border-gray-700 bg-gray-950 px-3 py-1.5 text-sm"
              />
              <Button size="sm" onClick={handleSave} disabled={saving}>
                Save
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
              {provider.configured ? "Change" : "Add key"}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function UsageBar({ usage }: { usage: ProviderUsage }) {
  if (!usage.requests_limit && !usage.tokens_limit) return null;
  const pct = usage.requests_limit
    ? Math.min(100, Math.round((usage.requests / usage.requests_limit) * 100))
    : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-400">
        <span>{usage.label}</span>
        <span>
          {usage.requests}
          {usage.requests_limit ? ` / ${usage.requests_limit} req` : " req"}
        </span>
      </div>
      {usage.requests_limit > 0 ? (
        <div className="h-1.5 overflow-hidden rounded-full bg-gray-800">
          <div
            className="h-full rounded-full bg-blue-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}

function RoutingTable({
  rows,
  showFallback,
}: {
  rows: AiConfigResponse["free_routing"];
  showFallback: boolean;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-gray-800 bg-gray-950 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Task</th>
            <th className="px-4 py-3">Quality</th>
            <th className="px-4 py-3">Model 1 (Primary)</th>
            {showFallback ? <th className="px-4 py-3">Fallback chain</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.task_type} className="border-b border-gray-800/60">
              <td className="px-4 py-3">{row.task_label}</td>
              <td className="px-4 py-3">
                <QualityStars count={row.quality_stars} />
              </td>
              <td className="px-4 py-3">{row.primary_model}</td>
              {showFallback ? (
                <td className="px-4 py-3 text-gray-400">
                  {row.fallback_chain ? `→ ${row.fallback_chain}` : "—"}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type ConfigTab = "guide" | "settings";

export default function AiConfigPage() {
  const [config, setConfig] = useState<AiConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<ConfigTab>("guide");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setConfig(await api.getAiConfig());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load AI config");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function setTier(tier: AiTier) {
    setBusy(true);
    try {
      setConfig(await api.setAiTier(tier));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update tier");
    } finally {
      setBusy(false);
    }
  }

  async function handleUseAllFree() {
    setBusy(true);
    try {
      setConfig(await api.useAllFree());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed");
    } finally {
      setBusy(false);
    }
  }

  async function saveProvider(provider: string, apiKey: string) {
    setConfig(await api.updateAiProvider(provider, apiKey, true));
  }

  if (loading) {
    return <p className="text-gray-400">Loading AI configuration…</p>;
  }

  if (!config) {
    return <p className="text-red-400">{error || "Unable to load configuration"}</p>;
  }

  const tier = config.ai_tier ?? (config.free_mode_enabled ? "free" : "premium");
  const routingRows =
    tier === "free"
      ? config.free_routing
      : tier === "low_cost"
        ? config.low_cost_routing
        : config.paid_routing;

  const premiumProvidersDisabled = tier !== "premium";

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">AI Configuration</h1>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-gray-700 p-1">
            {(
              [
                ["guide", "Usage guide"],
                ["settings", "Settings"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id)}
                className={`rounded-md px-3 py-1.5 text-sm ${
                  activeTab === id
                    ? "bg-gray-800 text-white"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {activeTab === "settings" ? (
            <Button
              onClick={handleUseAllFree}
              disabled={busy}
              className="bg-green-700 hover:bg-green-600"
            >
              Use all free — one-click setup
            </Button>
          ) : null}
        </div>
      </div>

      {error ? (
        <p className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-2 text-sm text-red-300">
          {error}
        </p>
      ) : null}

      {activeTab === "guide" ? (
        <AiUsageGuidePanel config={config} activeTier={tier} />
      ) : null}

      {activeTab === "settings" ? (
        <>
      <section className="rounded-xl border border-gray-700 bg-gray-900 p-6">
        <h2 className="mb-4 text-lg font-medium">Cost tier</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {TIER_CARDS.map((card) => {
            const active = tier === card.id;
            const border =
              card.id === "free"
                ? "border-green-600 bg-green-950/20"
                : card.id === "low_cost"
                  ? "border-amber-600 bg-amber-950/20"
                  : "border-orange-600 bg-orange-950/20";
            return (
              <button
                key={card.id}
                type="button"
                disabled={busy}
                onClick={() => setTier(card.id)}
                className={`rounded-lg border p-4 text-left transition ${
                  active ? border : "border-gray-700 bg-gray-950 hover:border-gray-600"
                }`}
              >
                <p className="font-semibold">
                  {card.badge} {card.name} {active ? "(Current)" : ""}
                </p>
                <p className="mt-1 text-sm text-gray-300">{card.summary}</p>
                <ul className="mt-2 space-y-1 text-xs text-gray-500">
                  {card.details.map((d) => (
                    <li key={d}>• {d}</li>
                  ))}
                </ul>
              </button>
            );
          })}
        </div>
      </section>

      {Object.keys(config.daily_usage ?? {}).length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-lg font-medium">Today&apos;s usage</h2>
          <div className="grid gap-3 rounded-xl border border-gray-800 p-4 md:grid-cols-2">
            {Object.entries(config.daily_usage)
              .filter(([, u]) => u.requests > 0 || u.requests_limit > 0)
              .map(([key, usage]) => (
                <UsageBar key={key} usage={usage} />
              ))}
          </div>
        </section>
      ) : null}

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Provider API keys</h2>
        <p className="text-sm text-gray-500">
          {tier === "premium"
            ? "Anthropic or OpenAI required for premium tier."
            : tier === "low_cost"
              ? "DeepSeek + optional Together for low cost. Free providers as fallback."
              : "OpenRouter required. Add Groq, Gemini, Cerebras for longer fallback chains."}
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          {config.providers.map((p) => {
            const isPremiumOnly = ["anthropic", "openai"].includes(p.provider);
            const disabled =
              (premiumProvidersDisabled && isPremiumOnly) ||
              (tier === "free" && isPremiumOnly);
            return (
              <ProviderCard
                key={p.provider}
                provider={p}
                disabled={disabled}
                onSave={(key) => saveProvider(p.provider, key)}
              />
            );
          })}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">
          {tier === "free"
            ? "Free mode routing (multi-provider chains)"
            : tier === "low_cost"
              ? "Low cost routing"
              : "Premium routing"}
        </h2>
        <RoutingTable rows={routingRows} showFallback={tier !== "premium"} />
        {tier !== "premium" ? (
          <p className="text-sm text-amber-400/90">
            Up to 15 models per task. Rate limited? PM Studio switches to the next model in ~1
            second. Architecture docs get 12 min per model before timeout.
          </p>
        ) : null}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">Per-screen model overrides</h2>
        <p className="text-sm text-gray-500">
          Users can also change models from each AI page via the model selector in the top-right.
        </p>
        <div className="rounded-xl border border-gray-800">
          {config.screen_models.map((sm) => (
            <div
              key={sm.screen}
              className="flex items-center justify-between border-b border-gray-800 px-4 py-3 last:border-0"
            >
              <span className="capitalize">{sm.screen}</span>
              <span className="text-sm text-gray-400">
                {sm.label}
                {sm.source === "override" ? " (override)" : ` (${sm.source})`}
              </span>
            </div>
          ))}
        </div>
      </section>
        </>
      ) : null}
    </div>
  );
}
