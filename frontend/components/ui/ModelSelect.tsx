"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type AiModelOption, type ModelChoice } from "@/lib/api";

const PROVIDER_ICONS: Record<string, string> = {
  anthropic: "🟣",
  openai: "🟢",
  openrouter: "🔵",
  groq: "⚡",
  together: "🤝",
  gemini: "✨",
  cerebras: "🔶",
  deepseek: "🌊",
  sambanova: "🔴",
  nvidia: "🟩",
  huggingface: "🤗",
  aimlapi: "🌐",
  siliconflow: "💎",
  alibaba: "☁️",
  github: "🐙",
};

const GROUP_LABELS: Record<string, string> = {
  premium: "Paid",
  low_cost: "Low cost",
  free: "Free",
};

const GROUP_ORDER = ["premium", "low_cost", "free"] as const;

export interface ModelSelectProps {
  value: ModelChoice | null;
  onChange: (value: ModelChoice | null) => void;
  className?: string;
  compact?: boolean;
}

export function ModelSelect({
  value,
  onChange,
  className = "",
  compact = false,
}: ModelSelectProps) {
  const [options, setOptions] = useState<AiModelOption[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.listAiModels();
        if (!cancelled) setOptions(data.models);
      } catch {
        if (!cancelled) setOptions([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const grouped = useMemo(() => {
    const map = new Map<string, AiModelOption[]>();
    for (const group of GROUP_ORDER) {
      const items = options.filter((o) => o.group === group);
      if (items.length > 0) map.set(group, items);
    }
    const other = options.filter(
      (o) => !GROUP_ORDER.includes(o.group as (typeof GROUP_ORDER)[number]),
    );
    if (other.length > 0) map.set("other", other);
    return map;
  }, [options]);

  const currentKey = value ? `${value.provider}:${value.model}` : "";

  return (
    <select
      aria-label="AI model"
      title={`Auto uses tier routing. ${options.length} models available.`}
      className={`rounded-md border border-gray-700 bg-gray-950 text-gray-200 ${
        compact ? "max-w-[12rem] px-2 py-1 text-xs" : "min-w-[14rem] max-w-[20rem] px-2 py-1.5 text-sm"
      } ${className}`}
      value={currentKey}
      disabled={loading}
      onChange={(e) => {
        const key = e.target.value;
        if (!key) {
          onChange(null);
          return;
        }
        const opt = options.find((o) => `${o.provider}:${o.model}` === key);
        if (opt) onChange({ provider: opt.provider, model: opt.model });
      }}
    >
      <option value="">Auto</option>
      {Array.from(grouped.entries()).map(([group, items]) => (
        <optgroup key={group} label={`${GROUP_LABELS[group] ?? group} (${items.length})`}>
          {items.map((opt) => (
            <option
              key={`${opt.provider}-${opt.model}`}
              value={`${opt.provider}:${opt.model}`}
              disabled={opt.available === false}
            >
              {PROVIDER_ICONS[opt.provider] ?? "•"} {opt.label}
              {opt.available === false ? " (no key)" : ""}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}

export function modelLabelFromProgress(raw?: string | null): string {
  return raw?.trim() || "Auto";
}
