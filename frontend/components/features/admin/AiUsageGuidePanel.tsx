"use client";

import type { AiConfigResponse, ProviderUsage } from "@/lib/api";

// ─── Reference numbers (medium project ≈ 20 Kanban tasks) ───────────────────

const PROJECT_PROFILE = {
  label: "Medium project",
  tasks: 20,
  aiCalls: 38,
  tokensMin: 800_000,
  tokensMax: 1_500_000,
  geminiCalls: 12,
  openrouterCalls: 15,
  groqCalls: 5,
};

const TIER_PLANS = {
  free: {
    id: "free" as const,
    badge: "🆓",
    name: "Free mode",
    costPerProject: "$0",
    costNote: "Together overflow ~$0.01–0.03/arch only if free pools dry",
    projectsPerDay: { min: 1, max: 3, label: "1–3 full projects / day" },
    projectsPerMonth: { min: 40, max: 70, label: "~40–70 / month (paced)" },
    reliability: "70–85%",
    highlight: "border-emerald-600/50 bg-emerald-950/20",
    accent: "text-emerald-400",
    bar: "bg-emerald-500",
  },
  low_cost: {
    id: "low_cost" as const,
    badge: "💙",
    name: "Low cost mode",
    costPerProject: "$0.15–0.35",
    costNote: "DeepSeek + GPT-4o Mini + Gemini paid · $10 credit ≈ 30–65 projects",
    projectsPerDay: { min: 3, max: 8, label: "3–8 full projects / day" },
    projectsPerMonth: { min: 30, max: 65, label: "30–65 with $10 OpenRouter credit" },
    reliability: "95%+",
    highlight: "border-blue-600/50 bg-blue-950/20",
    accent: "text-blue-400",
    bar: "bg-blue-500",
  },
  premium: {
    id: "premium" as const,
    badge: "🚀",
    name: "Premium mode",
    costPerProject: "$0.50–2.00",
    costNote: "Claude Sonnet/Opus + GPT-4o · budget-dependent",
    projectsPerDay: { min: 2, max: 10, label: "2–10 / day (budget-limited)" },
    projectsPerMonth: { min: 5, max: 20, label: "5–20 with typical API budget" },
    reliability: "99%",
    highlight: "border-purple-600/50 bg-purple-950/20",
    accent: "text-purple-400",
    bar: "bg-purple-500",
  },
};

const PROVIDER_LIMITS = [
  { icon: "🟦", name: "Gemini 2.5 Flash", requests: "1,500 / day", tokens: "250K / min", role: "Primary — PDF, PRD, SRS, arch" },
  { icon: "🔀", name: "OpenRouter free", requests: "1,000 / day*", tokens: "~20 req / min", role: "JSON, Laguna specs, Kimi extract" },
  { icon: "⚡", name: "Groq", requests: "1,000 / day / model", tokens: "6K–30K / min", role: "Fast fallback, orchestration" },
  { icon: "🧠", name: "Cerebras", requests: "Unlimited", tokens: "1M / day total", role: "Quick overflow JSON" },
  { icon: "🤝", name: "Together", requests: "Serverless", tokens: "Paid overflow", role: "~$0.10–0.88 / 1M when free dries" },
];

const PIPELINE_STEPS = [
  { day: 1, title: "Foundation", load: "light", calls: "~6", items: ["Upload PDF → analyze", "Synthesize feedback (if any)", "Generate PRD", "Generate SRS", "Stop — no architecture today"] },
  { day: 2, title: "Architecture", load: "heavy", calls: "~12", items: ["Generate Architecture Suite", "If fail → Resume (not full regenerate)", "Fix weak docs only", "Stop — no specs today"] },
  { day: 3, title: "Tasks & specs", load: "medium", calls: "~20+", items: ["Extract modules from SRS", "Generate specs in batches of 5–8", "2-hour breaks between batches", "Generate orchestration last"] },
];

const PER_ACTION_COST = [
  { action: "Requirement analyze", calls: 1, free: "$0", low: "$0*", premium: "$0.02" },
  { action: "PRD generate", calls: 1, free: "$0", low: "$0.02", premium: "$0.08" },
  { action: "SRS generate", calls: 1, free: "$0", low: "$0.03", premium: "$0.10" },
  { action: "Architecture suite", calls: "10–14", free: "$0", low: "$0.05", premium: "$0.40" },
  { action: "Module extract", calls: 1, free: "$0", low: "$0.02", premium: "$0.05" },
  { action: "Task spec (each)", calls: 1, free: "$0", low: "$0.01", premium: "$0.03" },
  { action: "Orchestration", calls: 1, free: "$0", low: "$0.04", premium: "$0.15" },
  { action: "Full project (20 tasks)", calls: "~38", free: "$0", low: "$0.15–0.35", premium: "$0.50–2.00" },
];

function fmtK(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toLocaleString();
}

function remainingFreeProjects(usage: Record<string, ProviderUsage> | null | undefined): {
  gemini: number;
  openrouter: number;
  realistic: number;
} {
  const gemini = usage?.gemini;
  const or = usage?.openrouter;
  const geminiLeft = Math.max(
    0,
    Math.floor(((gemini?.requests_limit ?? 1500) - (gemini?.requests ?? 0)) / PROJECT_PROFILE.geminiCalls),
  );
  const orLeft = Math.max(
    0,
    Math.floor(((or?.requests_limit ?? 1000) - (or?.requests ?? 0)) / PROJECT_PROFILE.openrouterCalls),
  );
  const realistic = Math.min(geminiLeft, orLeft, 3);
  return { gemini: geminiLeft, openrouter: orLeft, realistic };
}

function totalDailyUsage(usage: Record<string, ProviderUsage>): {
  requests: number;
  tokens: number;
} {
  return Object.values(usage).reduce(
    (acc, p) => ({
      requests: acc.requests + p.requests,
      tokens: acc.tokens + p.tokens_in + p.tokens_out,
    }),
    { requests: 0, tokens: 0 },
  );
}

function FlowDiagram() {
  const nodes = [
    { icon: "📋", label: "Upload PDF", sub: "req_analyze" },
    { icon: "📄", label: "PRD", sub: "prd_generate" },
    { icon: "📑", label: "SRS", sub: "srs_generate" },
    { icon: "🏗️", label: "Architecture ×6", sub: "arch_generate" },
    { icon: "✅", label: "Tasks + specs", sub: "module + spec" },
    { icon: "🎯", label: "Orchestration", sub: "master prompt" },
  ];

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-950/80 p-4">
      <p className="mb-4 text-xs font-medium uppercase tracking-wider text-gray-500">
        How AI routing works (end to end)
      </p>

      {/* User → Router */}
      <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2">You press AI button</span>
        <span className="text-gray-600">→</span>
        <span className="rounded-lg border border-blue-800/60 bg-blue-950/40 px-3 py-2 text-blue-300">
          Auto dropdown? → try chosen model first
        </span>
        <span className="text-gray-600">→</span>
        <span className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-3 py-2 text-emerald-300">
          Tier chain (up to 15 models)
        </span>
        <span className="text-gray-600">→</span>
        <span className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-2">Structured JSON saved</span>
      </div>

      {/* Pipeline */}
      <div className="flex min-w-[640px] items-stretch gap-1">
        {nodes.map((n, i) => (
          <div key={n.label} className="flex flex-1 items-center gap-1">
            <div className="flex flex-1 flex-col items-center rounded-lg border border-gray-700 bg-gray-900 px-2 py-3 text-center">
              <span className="text-lg">{n.icon}</span>
              <span className="mt-1 text-[11px] font-medium text-gray-200">{n.label}</span>
              <span className="text-[10px] text-gray-500">{n.sub}</span>
            </div>
            {i < nodes.length - 1 ? (
              <span className="shrink-0 text-gray-600">→</span>
            ) : null}
          </div>
        ))}
      </div>

      {/* Fallback logic */}
      <div className="mt-4 grid gap-2 sm:grid-cols-3 text-[11px]">
        <div className="rounded-lg border border-amber-800/40 bg-amber-950/20 px-3 py-2">
          <span className="font-medium text-amber-400">Rate limit 429</span>
          <p className="mt-0.5 text-gray-400">Cooldown 2 min → skip to next model</p>
        </div>
        <div className="rounded-lg border border-red-800/40 bg-red-950/20 px-3 py-2">
          <span className="font-medium text-red-400">Daily quota hit</span>
          <p className="mt-0.5 text-gray-400">Provider benched 1 hour → next pool</p>
        </div>
        <div className="rounded-lg border border-green-800/40 bg-green-950/20 px-3 py-2">
          <span className="font-medium text-green-400">Architecture fail</span>
          <p className="mt-0.5 text-gray-400">Resume picks up last chunk — no restart</p>
        </div>
      </div>
    </div>
  );
}

interface AiUsageGuidePanelProps {
  config: AiConfigResponse;
  activeTier: keyof typeof TIER_PLANS;
}

export function AiUsageGuidePanel({ config, activeTier }: AiUsageGuidePanelProps) {
  const usage = config.daily_usage;
  const remaining = remainingFreeProjects(usage);
  const configuredCount = config.providers.filter((p) => p.configured && p.is_enabled).length;
  const activePlan = TIER_PLANS[activeTier];

  return (
    <div className="space-y-6">

      {/* Hero summary */}
      <div className={`rounded-2xl border p-5 ${activePlan.highlight}`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm text-gray-400">Your active tier</p>
            <p className={`text-2xl font-bold ${activePlan.accent}`}>
              {activePlan.badge} {activePlan.name}
            </p>
            <p className="mt-1 text-sm text-gray-400">
              {configuredCount} provider keys active · {PROJECT_PROFILE.aiCalls} AI calls per full project
            </p>
          </div>
          {usage && activeTier === "free" && (
            <div className="rounded-xl border border-gray-700 bg-black/30 px-4 py-3 text-right">
              <p className="text-xs text-gray-500">Estimated left today (free)</p>
              <p className={`text-3xl font-bold ${activePlan.accent}`}>{remaining.realistic}</p>
              <p className="text-[10px] text-gray-500">full project{remaining.realistic !== 1 ? "s" : ""}</p>
            </div>
          )}
        </div>
      </div>

      {/* Tier comparison */}
      <section>
        <h3 className="mb-3 text-sm font-medium uppercase tracking-wider text-gray-500">
          Tier comparison — cost & capacity
        </h3>
        <div className="grid gap-4 lg:grid-cols-3">
          {(Object.keys(TIER_PLANS) as Array<keyof typeof TIER_PLANS>).map((key) => {
            const plan = TIER_PLANS[key];
            const isActive = key === activeTier;
            return (
              <div
                key={key}
                className={`rounded-xl border p-4 transition-all ${
                  isActive ? `${plan.highlight} ring-1 ring-white/10` : "border-gray-800 bg-gray-900/50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xl">{plan.badge}</span>
                  {isActive && (
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${plan.highlight} ${plan.accent}`}>
                      Active
                    </span>
                  )}
                </div>
                <p className="mt-2 font-semibold text-gray-100">{plan.name}</p>
                <div className="mt-3 space-y-2 text-sm">
                  <div className="flex justify-between gap-2">
                    <span className="text-gray-500">Cost / project</span>
                    <span className={`font-mono font-medium ${plan.accent}`}>{plan.costPerProject}</span>
                  </div>
                  <div className="flex justify-between gap-2">
                    <span className="text-gray-500">Projects / day</span>
                    <span className="text-gray-200">{plan.projectsPerDay.label}</span>
                  </div>
                  <div className="flex justify-between gap-2">
                    <span className="text-gray-500">Monthly pace</span>
                    <span className="text-gray-400 text-xs">{plan.projectsPerMonth.label}</span>
                  </div>
                  <div className="flex justify-between gap-2">
                    <span className="text-gray-500">Reliability</span>
                    <span className="text-gray-300">{plan.reliability}</span>
                  </div>
                </div>
                <p className="mt-3 text-[11px] leading-relaxed text-gray-500">{plan.costNote}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Project math */}
      <section>
        <h3 className="mb-3 text-sm font-medium uppercase tracking-wider text-gray-500">
          One full project — what it consumes ({PROJECT_PROFILE.label}, {PROJECT_PROFILE.tasks} tasks)
        </h3>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: "AI calls", value: `~${PROJECT_PROFILE.aiCalls}`, sub: "req → PRD → SRS → arch → specs" },
            { label: "Tokens", value: `${fmtK(PROJECT_PROFILE.tokensMin)}–${fmtK(PROJECT_PROFILE.tokensMax)}`, sub: "in + out across providers" },
            { label: "Gemini calls", value: `~${PROJECT_PROFILE.geminiCalls}`, sub: "heaviest on architecture day" },
            { label: "Time (free)", value: "2–4 hours", sub: "spread over 3 days recommended" },
          ].map((stat) => (
            <div key={stat.label} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <p className="text-xs text-gray-500">{stat.label}</p>
              <p className="mt-1 text-xl font-bold text-gray-100">{stat.value}</p>
              <p className="mt-1 text-[11px] text-gray-500">{stat.sub}</p>
            </div>
          ))}
        </div>

        {usage && activeTier === "free" && (
          <div className="mt-3 rounded-xl border border-gray-800 bg-gray-950 p-4 text-sm">
            <p className="mb-2 font-medium text-gray-300">Today&apos;s remaining capacity (calculated)</p>
            <div className="grid gap-2 sm:grid-cols-3 text-xs">
              <div className="flex justify-between rounded-lg bg-gray-900 px-3 py-2">
                <span className="text-gray-500">From Gemini quota</span>
                <span className="font-mono text-emerald-400">~{remaining.gemini} projects</span>
              </div>
              <div className="flex justify-between rounded-lg bg-gray-900 px-3 py-2">
                <span className="text-gray-500">From OpenRouter quota</span>
                <span className="font-mono text-purple-400">~{remaining.openrouter} projects</span>
              </div>
              <div className="flex justify-between rounded-lg bg-gray-900 px-3 py-2">
                <span className="text-gray-500">Realistic (TPM limits)</span>
                <span className="font-mono text-amber-400">~{remaining.realistic} projects</span>
              </div>
            </div>
            <p className="mt-2 text-[11px] text-gray-500">
              Used today: {totalDailyUsage(usage).requests.toLocaleString()} requests ·{" "}
              {fmtK(totalDailyUsage(usage).tokens)} tokens
            </p>
          </div>
        )}
      </section>

      {/* Per-action cost table */}
      <section>
        <h3 className="mb-3 text-sm font-medium uppercase tracking-wider text-gray-500">
          Cost per action (all tiers)
        </h3>
        <div className="overflow-x-auto rounded-xl border border-gray-800">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-gray-800 bg-gray-950 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-2.5">Action</th>
                <th className="px-4 py-2.5">Calls</th>
                <th className="px-4 py-2.5 text-emerald-400">Free</th>
                <th className="px-4 py-2.5 text-blue-400">Low cost</th>
                <th className="px-4 py-2.5 text-purple-400">Premium</th>
              </tr>
            </thead>
            <tbody>
              {PER_ACTION_COST.map((row) => (
                <tr key={row.action} className="border-t border-gray-800/60 hover:bg-gray-900/50">
                  <td className="px-4 py-2.5 font-medium">{row.action}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-gray-400">{row.calls}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-emerald-400">{row.free}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-blue-400">{row.low}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-purple-400">{row.premium}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] text-gray-500">* Requirements can stay on free Gemini even in low_cost tier.</p>
      </section>

      {/* Free provider limits */}
      <section>
        <h3 className="mb-3 text-sm font-medium uppercase tracking-wider text-gray-500">
          Free mode — provider daily limits
        </h3>
        <div className="overflow-x-auto rounded-xl border border-gray-800">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-gray-800 bg-gray-950 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-2.5">Provider</th>
                <th className="px-4 py-2.5">Requests</th>
                <th className="px-4 py-2.5">Tokens</th>
                <th className="px-4 py-2.5">Role in chain</th>
              </tr>
            </thead>
            <tbody>
              {PROVIDER_LIMITS.map((p) => (
                <tr key={p.name} className="border-t border-gray-800/60">
                  <td className="px-4 py-2.5">
                    <span className="mr-1.5">{p.icon}</span>
                    {p.name}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-gray-300">{p.requests}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-gray-300">{p.tokens}</td>
                  <td className="px-4 py-2.5 text-xs text-gray-400">{p.role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] text-gray-500">* OpenRouter 1,000/day assumes $10+ credits (you have this).</p>
      </section>

      {/* How to use */}
      <section>
        <h3 className="mb-3 text-sm font-medium uppercase tracking-wider text-gray-500">
          How to use — 3-day playbook (stay inside free limits)
        </h3>
        <div className="grid gap-4 md:grid-cols-3">
          {PIPELINE_STEPS.map((step) => {
            const loadColor =
              step.load === "light" ? "border-green-800/50 bg-green-950/20"
              : step.load === "heavy" ? "border-red-800/50 bg-red-950/20"
              : "border-amber-800/50 bg-amber-950/20";
            const loadLabel =
              step.load === "light" ? "🟢 Light" : step.load === "heavy" ? "🔴 Heavy" : "🟡 Medium";
            return (
              <div key={step.day} className={`rounded-xl border p-4 ${loadColor}`}>
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-gray-100">Day {step.day} — {step.title}</span>
                  <span className="text-[10px] text-gray-400">{loadLabel}</span>
                </div>
                <p className="mt-1 font-mono text-xs text-gray-500">~{step.calls} AI calls</p>
                <ul className="mt-3 space-y-1.5 text-xs text-gray-300">
                  {step.items.map((item) => (
                    <li key={item} className="flex gap-2">
                      <span className="text-gray-600">•</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-green-800/40 bg-green-950/10 p-4">
            <p className="text-sm font-medium text-green-400">Do</p>
            <ul className="mt-2 space-y-1 text-xs text-gray-400">
              <li>• Keep model dropdown on <strong className="text-gray-300">Auto</strong></li>
              <li>• Use <strong className="text-gray-300">Resume</strong> after architecture failures</li>
              <li>• Generate specs in batches of 5–8 with breaks</li>
              <li>• Switch to <strong className="text-gray-300">low_cost</strong> when you want to spend OpenRouter $10</li>
            </ul>
          </div>
          <div className="rounded-xl border border-red-800/40 bg-red-950/10 p-4">
            <p className="text-sm font-medium text-red-400">Don&apos;t</p>
            <ul className="mt-2 space-y-1 text-xs text-gray-400">
              <li>• Run full suite + 20 specs in one sitting on free tier</li>
              <li>• Full regenerate architecture after partial progress</li>
              <li>• Pick a manual model unless one job keeps failing</li>
              <li>• Expect premium quality while on free tier</li>
            </ul>
          </div>
        </div>
      </section>

      {/* Flow diagram */}
      <FlowDiagram />

      {/* Quick links */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 px-4 py-3 text-xs text-gray-400">
        <span className="font-medium text-gray-300">Where to control this: </span>
        Tier cards above switch free / low_cost / premium ·
        <span className="text-gray-300"> Auto dropdown</span> on each AI page overrides one action ·
        <span className="text-gray-300"> Daily usage</span> section shows live quota consumption
      </div>
    </div>
  );
}
