"use client";

import { useCallback, useEffect, useState } from "react";
import { AiUsageGuidePanel } from "@/components/features/admin/AiUsageGuidePanel";
import { AiChainStatusPanel } from "@/components/features/admin/AiChainStatusPanel";
import { Button } from "@/components/ui/button";
import { QualityStars } from "@/components/ui/ScreenModelSelector";
import {
  api,
  type AiConfigResponse,
  type AiProviderStatus,
  type AiTier,
  type ModelCatalogEntry,
  type ProviderUsage,
  type TierModelCatalog,
} from "@/lib/api";

const TIER_BADGE: Record<string, string> = {
  free: "🆓",
  low_cost: "💰",
  premium: "💳",
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
      "15 providers: Gemini, OpenRouter, Groq, SiliconFlow, HF, GitHub…",
      "Up to 20-model fallback per task",
      "Best for dev and testing",
    ],
  },
  {
    id: "low_cost",
    badge: "💰",
    name: "Low cost mode",
    summary: "~$0.05–0.15 per project",
    details: [
      "DeepSeek + AIML API + Alibaba Qwen primary",
      "Together / AIML as fast paid backup",
      "Full free pool as zero-cost fallback",
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
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium">
          {provider.label ?? provider.provider}
          {provider.default_tier ? (
            <span className="ml-2 text-xs text-gray-500">
              {TIER_BADGE[provider.default_tier] ?? ""} {provider.default_tier}
            </span>
          ) : null}
        </h3>
        <span
          className={`shrink-0 text-xs ${
            provider.configured ? "text-green-400" : "text-gray-500"
          }`}
        >
          {provider.configured ? "● CONFIGURED" : "○ NOT SET"}
        </span>
      </div>
      {provider.note ? (
        <p className="mt-1 text-xs text-gray-500">{provider.note}</p>
      ) : null}
      {provider.masked_key && !editing ? (
        <p className="mt-2 text-sm text-gray-400">API Key: {provider.masked_key}</p>
      ) : null}
      {!disabled && (
        <div className="mt-3 flex flex-wrap gap-2">
          {provider.signup_url ? (
            <a
              href={provider.signup_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-gray-700 px-3 py-1.5 text-xs text-blue-400 hover:bg-gray-800"
            >
              Get API key ↗
            </a>
          ) : null}
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

function fmtNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function UsageBar({ usage }: { usage: ProviderUsage }) {
  const totalTokens = (usage.tokens_in ?? 0) + (usage.tokens_out ?? 0);
  const hasActivity = usage.requests > 0 || totalTokens > 0;
  if (!hasActivity && !usage.requests_limit && !usage.tokens_limit) return null;

  const COLOR_MAP: Record<string, string> = {
    purple: "bg-purple-500", orange: "bg-orange-500", blue: "bg-blue-500",
    cyan: "bg-cyan-500", pink: "bg-pink-500", green: "bg-green-500",
    indigo: "bg-indigo-500", red: "bg-red-500", emerald: "bg-emerald-500",
    yellow: "bg-yellow-500", teal: "bg-teal-500", violet: "bg-violet-500",
    gray: "bg-gray-500",
  };
  const barColor = COLOR_MAP[usage.color ?? "gray"] ?? "bg-blue-500";

  const reqPct = usage.requests_limit > 0
    ? Math.min(100, Math.round((usage.requests / usage.requests_limit) * 100)) : 0;
  const tokPct = usage.tokens_limit > 0
    ? Math.min(100, Math.round((totalTokens / usage.tokens_limit) * 100)) : 0;

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950/60 p-3 space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-200">{usage.label}</span>
        {usage.requests_limit > 0 && (
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${
            reqPct >= 90 ? "border-red-800/50 bg-red-950/40 text-red-400"
            : reqPct >= 70 ? "border-amber-800/50 bg-amber-950/40 text-amber-400"
            : "border-gray-700 bg-gray-900 text-gray-400"
          }`}>{reqPct}% used</span>
        )}
      </div>

      {/* Stat row */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-base font-bold tabular-nums text-white">{fmtNum(usage.requests)}</p>
          <p className="text-[10px] text-gray-600">
            {usage.requests_limit > 0 ? `/ ${fmtNum(usage.requests_limit)} req` : "requests"}
          </p>
        </div>
        <div>
          <p className="text-base font-bold tabular-nums text-blue-300">{fmtNum(usage.tokens_in ?? 0)}</p>
          <p className="text-[10px] text-gray-600">tokens in</p>
        </div>
        <div>
          <p className="text-base font-bold tabular-nums text-emerald-300">{fmtNum(usage.tokens_out ?? 0)}</p>
          <p className="text-[10px] text-gray-600">tokens out</p>
        </div>
      </div>

      {/* Request limit bar */}
      {usage.requests_limit > 0 && (
        <div>
          <div className="flex justify-between text-[10px] text-gray-600 mb-0.5">
            <span>Daily request limit</span><span>{reqPct}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-gray-800">
            <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${reqPct}%` }} />
          </div>
        </div>
      )}

      {/* Token limit bar */}
      {usage.tokens_limit > 0 && (
        <div>
          <div className="flex justify-between text-[10px] text-gray-600 mb-0.5">
            <span>Daily token limit</span><span>{fmtNum(totalTokens)} / {fmtNum(usage.tokens_limit)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-gray-800">
            <div className="h-full rounded-full bg-purple-500 transition-all" style={{ width: `${tokPct}%` }} />
          </div>
        </div>
      )}
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

type CatalogView = "all" | "configured";
type CatalogTier = "free" | "low_cost" | "premium";

const CATALOG_TIER_TABS: { id: CatalogTier; label: string; color: string }[] = [
  { id: "free", label: "Free", color: "text-green-400" },
  { id: "low_cost", label: "Low cost", color: "text-amber-400" },
  { id: "premium", label: "Paid", color: "text-orange-400" },
];

function ModelCatalogTable({ models }: { models: ModelCatalogEntry[] }) {
  if (models.length === 0) {
    return (
      <p className="px-4 py-6 text-sm text-gray-500">
        No models in this category for the selected view.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-gray-800 bg-gray-950 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Model</th>
            <th className="px-4 py-3">Provider</th>
            <th className="px-4 py-3">Context</th>
            <th className="px-4 py-3">Cost</th>
            <th className="px-4 py-3">Routing</th>
            <th className="px-4 py-3">Key</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr
              key={`${m.provider}-${m.model}`}
              className="border-b border-gray-800/60"
            >
              <td className="px-4 py-2.5 font-medium">{m.label}</td>
              <td className="px-4 py-2.5 text-gray-400">{m.provider}</td>
              <td className="px-4 py-2.5 text-gray-400">{m.context || "—"}</td>
              <td className="px-4 py-2.5">{m.cost || "—"}</td>
              <td className="px-4 py-2.5">
                {m.in_routing ? (
                  <span className="text-xs text-blue-400">
                    {m.task_types.length > 0
                      ? m.task_types.slice(0, 2).join(", ") +
                        (m.task_types.length > 2
                          ? ` +${m.task_types.length - 2}`
                          : "")
                      : "Yes"}
                  </span>
                ) : (
                  <span className="text-gray-600">—</span>
                )}
              </td>
              <td className="px-4 py-2.5">
                {m.available ? (
                  <span className="text-green-400">● Ready</span>
                ) : (
                  <span className="text-gray-600">○ No key</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ModelCatalogSection({
  catalog,
  configuredCatalog,
}: {
  catalog: TierModelCatalog;
  configuredCatalog: TierModelCatalog;
}) {
  const [view, setView] = useState<CatalogView>("configured");
  const [tierTab, setTierTab] = useState<CatalogTier>("free");

  const activeCatalog = view === "configured" ? configuredCatalog : catalog;
  const models = activeCatalog[tierTab] ?? [];
  const counts = {
    free: activeCatalog.free?.length ?? 0,
    low_cost: activeCatalog.low_cost?.length ?? 0,
    premium: activeCatalog.premium?.length ?? 0,
  };
  const total = counts.free + counts.low_cost + counts.premium;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium">Model catalog</h2>
          <p className="text-sm text-gray-500">
            {total} models across free, low cost, and paid tiers
          </p>
        </div>
        <div className="flex rounded-lg border border-gray-700 p-1">
          {(
            [
              ["all", "All PM Studio models"],
              ["configured", "Configured providers only"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setView(id)}
              className={`rounded-md px-3 py-1.5 text-xs ${
                view === id
                  ? "bg-gray-800 text-white"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {CATALOG_TIER_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setTierTab(tab.id)}
            className={`rounded-lg border px-4 py-2 text-sm ${
              tierTab === tab.id
                ? "border-gray-600 bg-gray-800"
                : "border-gray-800 bg-gray-950 hover:border-gray-700"
            }`}
          >
            <span className={tab.color}>{tab.label}</span>
            <span className="ml-2 text-gray-500">({counts[tab.id]})</span>
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-gray-800">
        <ModelCatalogTable models={models} />
      </div>
    </section>
  );
}

type ConfigTab = "guide" | "settings" | "status";

function GithubSection() {
  const [cfg, setCfg] = useState<{ configured: boolean; masked_token: string | null; owner: string | null; source: string } | null>(null);
  const [token, setToken] = useState("");
  const [owner, setOwner] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [verify, setVerify] = useState<{
    ok: boolean;
    login?: string | null;
    token_type?: string;
    checks?: Record<string, "pass" | "fail" | "unknown">;
    message?: string;
  } | null>(null);

  useEffect(() => {
    api.getGithubConfig().then((c) => { setCfg(c); setOwner(c.owner ?? ""); }).catch(() => {});
  }, []);

  async function runVerify() {
    setVerifying(true);
    try {
      setVerify(await api.verifyGithub());
    } catch (e) {
      setVerify({ ok: false, message: e instanceof Error ? e.message : "Verification failed" });
    } finally {
      setVerifying(false);
    }
  }

  async function save() {
    setSaving(true);
    setMsg("");
    try {
      const c = await api.setGithubConfig(token.trim() ? token.trim() : null, owner.trim() || null);
      setCfg(c);
      setToken("");
      setEditing(false);
      setMsg("Saved — restart not needed.");
      // Validate the token's permissions immediately so problems surface here,
      // not 20 minutes into a build.
      await runVerify();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-medium">GitHub (Build code factory)</h2>
      <p className="text-sm text-gray-500">
        Token used by the Build screen to create repos and push generated code (CI runs there).
        Needs a fine-grained PAT with Administration + Contents + Workflows write access.
      </p>
      <div className="max-w-xl rounded-lg border border-gray-800 bg-gray-950/60 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-200">GitHub repo token</span>
          <span className={`text-xs font-medium ${cfg?.configured ? "text-green-400" : "text-gray-500"}`}>
            {cfg?.configured ? `● CONFIGURED (${cfg.source})` : "○ NOT SET"}
          </span>
        </div>
        {cfg?.masked_token && !editing ? (
          <p className="text-sm text-gray-400">Token: {cfg.masked_token}</p>
        ) : null}

        <label className="block text-xs text-gray-500">
          GitHub username / owner
          <input
            className="mt-1 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-gray-200"
            placeholder="e.g. SabyaSachee-AI"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
          />
        </label>

        {editing || !cfg?.configured ? (
          <label className="block text-xs text-gray-500">
            Fine-grained PAT
            <input
              type="password"
              className="mt-1 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 font-mono text-sm text-gray-200"
              placeholder="github_pat_…"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </label>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <a
            href="https://github.com/settings/personal-access-tokens"
            target="_blank"
            rel="noreferrer"
            className="rounded border border-gray-700 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-900"
          >
            Create token ↗
          </a>
          {cfg?.configured && !editing ? (
            <button onClick={() => setEditing(true)} className="rounded border border-gray-700 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-900">
              Change token
            </button>
          ) : null}
          <button
            onClick={() => void save()}
            disabled={saving}
            className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
          {cfg?.configured ? (
            <button
              onClick={() => void runVerify()}
              disabled={verifying}
              className="rounded border border-gray-700 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-900 disabled:opacity-50"
            >
              {verifying ? "Verifying…" : "Verify token"}
            </button>
          ) : null}
          {msg ? <span className="text-xs text-gray-400">{msg}</span> : null}
        </div>

        {verify ? (
          <div className={`rounded border p-3 text-xs ${
            verify.ok && !Object.values(verify.checks ?? {}).includes("fail")
              ? "border-emerald-900/50 bg-emerald-950/20"
              : "border-amber-900/50 bg-amber-950/20"
          }`}>
            <p className="mb-2 text-gray-300">{verify.message}</p>
            {verify.checks ? (
              <ul className="space-y-0.5">
                {([
                  ["auth", "Authentication"],
                  ["contents", "Contents (read & write)"],
                  ["workflows", "Workflows (read & write)"],
                  ["actions_read", "Actions: Read (CI status)"],
                ] as const).map(([key, label]) => {
                  const v = verify.checks?.[key];
                  if (!v) return null;
                  const icon = v === "pass" ? "✓" : v === "fail" ? "✕" : "?";
                  const cls = v === "pass" ? "text-emerald-400" : v === "fail" ? "text-red-400" : "text-gray-500";
                  return (
                    <li key={key} className="flex items-center gap-2">
                      <span className={`font-bold ${cls}`}>{icon}</span>
                      <span className="text-gray-400">{label}</span>
                      {v === "unknown" ? <span className="text-gray-600">(can't verify without a pushed repo)</span> : null}
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function VpsSection() {
  const [cfg, setCfg] = useState<{ configured: boolean; host: string | null; user: string | null; path: string | null; has_key: boolean } | null>(null);
  const [host, setHost] = useState("");
  const [user, setUser] = useState("");
  const [path, setPath] = useState("");
  const [sshKey, setSshKey] = useState("");
  const [editingKey, setEditingKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.getVpsConfig().then((c) => {
      setCfg(c); setHost(c.host ?? ""); setUser(c.user ?? ""); setPath(c.path ?? "");
    }).catch(() => {});
  }, []);

  async function save() {
    setSaving(true);
    setMsg("");
    try {
      const body: { host?: string; user?: string; ssh_key?: string; path?: string } = {
        host, user, path,
      };
      if (sshKey.trim()) body.ssh_key = sshKey;
      const c = await api.setVpsConfig(body);
      setCfg(c); setSshKey(""); setEditingKey(false); setMsg("Saved.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-medium">VPS deploy (Contabo)</h2>
      <p className="text-sm text-gray-500">
        Where generated apps deploy. PM Studio sets these as repo secrets and runs the
        deploy workflow (SSH → <code>git pull &amp;&amp; docker compose up -d --build</code>).
      </p>
      <div className="max-w-xl rounded-lg border border-gray-800 bg-gray-950/60 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-gray-200">VPS target</span>
          <span className={`text-xs font-medium ${cfg?.configured ? "text-green-400" : "text-gray-500"}`}>
            {cfg?.configured ? "● CONFIGURED" : "○ NOT SET"}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="block text-xs text-gray-500">Host / IP
            <input className="mt-1 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-gray-200" value={host} onChange={(e) => setHost(e.target.value)} placeholder="123.45.67.89" />
          </label>
          <label className="block text-xs text-gray-500">SSH user
            <input className="mt-1 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-gray-200" value={user} onChange={(e) => setUser(e.target.value)} placeholder="root or deploy" />
          </label>
        </div>
        <label className="block text-xs text-gray-500">App path on VPS
          <input className="mt-1 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 font-mono text-sm text-gray-200" value={path} onChange={(e) => setPath(e.target.value)} placeholder="/opt/myapp" />
        </label>
        {editingKey || !cfg?.has_key ? (
          <label className="block text-xs text-gray-500">SSH private key
            <textarea className="mt-1 h-24 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 font-mono text-xs text-gray-200" value={sshKey} onChange={(e) => setSshKey(e.target.value)} placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" />
          </label>
        ) : (
          <p className="text-xs text-gray-500">SSH key: <span className="text-green-400">stored</span> · <button onClick={() => setEditingKey(true)} className="underline">replace</button></p>
        )}
        <div className="flex items-center gap-2">
          <button onClick={() => void save()} disabled={saving} className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-50">
            {saving ? "Saving…" : "Save"}
          </button>
          {msg ? <span className="text-xs text-gray-400">{msg}</span> : null}
        </div>
      </div>
    </section>
  );
}

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
  const configuredCount = config.providers.filter((p) => p.configured).length;

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
                ["status", "Live status"],
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

      {activeTab === "status" ? <AiChainStatusPanel /> : null}

      {activeTab === "settings" ? (
        <>
      {configuredCount > 0 ? (
        <p className="rounded-lg border border-green-800/60 bg-green-950/30 px-4 py-2 text-sm text-green-300">
          {configuredCount} of {config.providers.length} providers configured — fallback
          chains and model dropdowns use all keys you added.
        </p>
      ) : null}

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

      {(() => {
        const usageEntries = Object.entries(config.daily_usage ?? {});
        const activeEntries = usageEntries.filter(([, u]) => {
          const total = (u.tokens_in ?? 0) + (u.tokens_out ?? 0);
          return u.requests > 0 || total > 0;
        });
        const totalRequests = activeEntries.reduce((s, [, u]) => s + u.requests, 0);
        const totalTokensIn  = activeEntries.reduce((s, [, u]) => s + (u.tokens_in ?? 0), 0);
        const totalTokensOut = activeEntries.reduce((s, [, u]) => s + (u.tokens_out ?? 0), 0);
        const showEntries = activeEntries.length > 0
          ? activeEntries
          : usageEntries.filter(([, u]) => u.requests_limit > 0 || u.tokens_limit > 0);

        return (
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium">Today&apos;s usage</h2>
              <span className="text-xs text-gray-500">resets at midnight UTC</span>
            </div>

            {/* Summary banner — only when there is activity */}
            {activeEntries.length > 0 && (
              <div className="grid grid-cols-3 gap-3 rounded-xl border border-gray-800 bg-gray-900/40 p-4">
                <div className="text-center">
                  <p className="text-2xl font-bold tabular-nums text-white">{fmtNum(totalRequests)}</p>
                  <p className="text-xs text-gray-500">total requests today</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold tabular-nums text-blue-300">{fmtNum(totalTokensIn)}</p>
                  <p className="text-xs text-gray-500">total tokens in</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold tabular-nums text-emerald-300">{fmtNum(totalTokensOut)}</p>
                  <p className="text-xs text-gray-500">total tokens out</p>
                </div>
              </div>
            )}

            {showEntries.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {showEntries.map(([key, usage]) => (
                  <UsageBar key={key} usage={usage} />
                ))}
              </div>
            ) : (
              <p className="rounded-xl border border-dashed border-gray-800 px-6 py-8 text-center text-sm text-gray-600">
                No AI requests made today yet — usage will appear here once the first AI call is made.
              </p>
            )}
          </section>
        );
      })()}

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Provider API keys</h2>
        <p className="text-sm text-gray-500">
          Add keys for any provider to expand your fallback chain. Free-tier providers
          (OpenRouter, Gemini, Groq, Hugging Face, SiliconFlow, GitHub Models, etc.)
          cost $0. Low-cost providers (DeepSeek, AIML API, Together) start around
          $0.14/1M tokens. Premium uses Anthropic or OpenAI.
        </p>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {config.providers.map((p) => {
            const isPremiumOnly = ["anthropic", "openai"].includes(p.provider);
            const disabled = tier !== "premium" && isPremiumOnly;
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

      <GithubSection />
      <VpsSection />

      {config.model_catalog ? (
        <ModelCatalogSection
          catalog={config.model_catalog}
          configuredCatalog={config.configured_model_catalog}
        />
      ) : null}

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
            Up to 20 models per task across 15 providers. Rate limited? PM Studio
            switches to the next model in ~1 second. Architecture docs get 12 min per
            model before timeout.
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
