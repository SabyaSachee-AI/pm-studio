"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { QualityStars } from "@/components/ui/ScreenModelSelector";
import {
  api,
  type AiConfigResponse,
  type AiProviderStatus,
} from "@/lib/api";

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

  const labels: Record<string, string> = {
    anthropic: "Anthropic (Claude)",
    openai: "OpenAI (GPT)",
    openrouter: "OpenRouter",
  };

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
        <h3 className="font-medium">{labels[provider.provider] ?? provider.provider}</h3>
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
              <Button
                size="sm"
                variant="outline"
                onClick={() => setEditing(false)}
              >
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

function RoutingTable({
  rows,
  freeMode,
}: {
  rows: AiConfigResponse["free_routing"];
  freeMode: boolean;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-gray-800 bg-gray-950 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Task</th>
            <th className="px-4 py-3">Quality</th>
            <th className="px-4 py-3">Model 1 (Primary)</th>
            {freeMode ? <th className="px-4 py-3">If rate limited</th> : null}
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
              {freeMode ? (
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

export default function AiConfigPage() {
  const [config, setConfig] = useState<AiConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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

  async function toggleFreeMode(enabled: boolean) {
    setBusy(true);
    try {
      setConfig(await api.setFreeMode(enabled));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update mode");
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

  const openrouter = config.providers.find((p) => p.provider === "openrouter");
  const freeActive = config.free_mode_enabled;

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">AI Configuration</h1>
        <Button
          onClick={handleUseAllFree}
          disabled={busy}
          className="bg-green-700 hover:bg-green-600"
        >
          Use All Free — One-Click Setup
        </Button>
      </div>

      {error ? (
        <p className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-2 text-sm text-red-300">
          {error}
        </p>
      ) : null}

      {/* Section 0 — Cost Mode */}
      <section className="rounded-xl border border-gray-700 bg-gray-900 p-6">
        <h2 className="mb-4 text-lg font-medium">💰 Cost Mode</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div
            className={`rounded-lg border p-4 ${
              !freeActive
                ? "border-orange-600 bg-orange-950/20"
                : "border-gray-700 bg-gray-950"
            }`}
          >
            <p className="font-semibold">💳 PAID MODE {!freeActive ? "(Current)" : ""}</p>
            <ul className="mt-2 space-y-1 text-sm text-gray-400">
              <li>Claude + OpenAI</li>
              <li>Best quality</li>
              <li>~$0.50/project</li>
            </ul>
          </div>
          <div
            className={`rounded-lg border p-4 ${
              freeActive
                ? "border-green-600 bg-green-950/20"
                : "border-gray-700 bg-gray-950"
            }`}
          >
            <p className="font-semibold">🆓 FREE MODE {freeActive ? "(Current)" : ""}</p>
            <ul className="mt-2 space-y-1 text-sm text-gray-400">
              <li>100% FREE — Zero cost</li>
              <li>OpenRouter free models</li>
              <li>Only OpenRouter key needed</li>
              <li>Llama 4 Maverick primary</li>
              <li>Quality: Good (not perfect)</li>
            </ul>
          </div>
        </div>
        <div className="mt-4">
          {freeActive ? (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => toggleFreeMode(false)}
            >
              Switch to PAID Mode
            </Button>
          ) : (
            <Button
              disabled={busy}
              onClick={() => toggleFreeMode(true)}
              className="bg-green-700 hover:bg-green-600"
            >
              Switch to FREE Mode
            </Button>
          )}
        </div>
      </section>

      {freeActive ? (
        <div className="rounded-xl border border-green-700 bg-green-950/30 px-4 py-3 text-sm text-green-200">
          🆓 Free Mode Active — Using OpenRouter free models. Only your OpenRouter API key is
          needed. Get a free key at{" "}
          <a
            href="https://openrouter.ai"
            target="_blank"
            rel="noreferrer"
            className="underline"
          >
            openrouter.ai
          </a>{" "}
          (no credit card required).
        </div>
      ) : null}

      {/* Provider keys */}
      <section className="space-y-4">
        <h2 className="text-lg font-medium">Provider API Keys</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <ProviderCard
            provider={config.providers.find((p) => p.provider === "anthropic")!}
            disabled={freeActive}
            onSave={(key) => saveProvider("anthropic", key)}
          />
          <ProviderCard
            provider={config.providers.find((p) => p.provider === "openai")!}
            disabled={freeActive}
            onSave={(key) => saveProvider("openai", key)}
          />
          <ProviderCard
            provider={openrouter!}
            disabled={false}
            onSave={(key) => saveProvider("openrouter", key)}
          />
        </div>
        {freeActive && openrouter?.configured ? (
          <p className="text-sm text-gray-500">
            This month: 0 calls | $0.00 (free!)
          </p>
        ) : null}
      </section>

      {/* Routing table */}
      <section className="space-y-3">
        <h2 className="text-lg font-medium">
          {freeActive ? "Free Mode Routing" : "Default Paid Routing"}
        </h2>
        <RoutingTable
          rows={freeActive ? config.free_routing : config.paid_routing}
          freeMode={freeActive}
        />
        {freeActive ? (
          <p className="text-sm text-amber-400/90">
            ⚠️ Free models are rate limited. If one model fails, PM Studio automatically tries
            the next free model. For best results, use during off-peak hours.
          </p>
        ) : null}
      </section>

      {/* Screen overrides summary */}
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Per-Screen Model Overrides</h2>
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
                {sm.source === "override" ? " (override)" : ""}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
