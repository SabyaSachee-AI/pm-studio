"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type AiModelOption, type ScreenModelInfo } from "@/lib/api";

type ScreenKey = "requirements" | "prds" | "srs" | "architecture" | "tasks";

interface ScreenModelSelectorProps {
  screen: ScreenKey;
  className?: string;
}

const GROUP_SECTIONS: Array<{
  key: "premium" | "low_cost" | "free";
  label: string;
  colorClass: string;
  icon: string;
}> = [
  { key: "premium", label: "Paid", colorClass: "text-orange-400", icon: "🟠" },
  { key: "low_cost", label: "Low cost", colorClass: "text-amber-400", icon: "💰" },
  { key: "free", label: "Free", colorClass: "text-green-400", icon: "🆓" },
];

const PROVIDER_ICONS: Record<string, string> = {
  anthropic: "🟣",
  openai: "🟢",
  openrouter: "🔵",
  groq: "⚡",
  gemini: "✨",
  cerebras: "🔶",
  deepseek: "🌊",
  together: "🤝",
  sambanova: "🔴",
  nvidia: "🟩",
  huggingface: "🤗",
  aimlapi: "🌐",
  siliconflow: "💎",
  alibaba: "☁️",
  github: "🐙",
};

function ModelOptionButton({
  opt,
  selected,
  onSelect,
}: {
  opt: AiModelOption;
  selected: boolean;
  onSelect: () => void;
}) {
  const icon = PROVIDER_ICONS[opt.provider] ?? "•";
  const disabled = opt.available === false;
  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      className={`mb-1 flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-gray-900 disabled:cursor-not-allowed disabled:opacity-40 ${
        selected ? "bg-gray-900 ring-1 ring-blue-600" : ""
      }`}
    >
      <span className="truncate pr-2">
        {selected ? "●" : "○"} {icon} {opt.label}
        {disabled ? " (no key)" : ""}
      </span>
      <span className="shrink-0 text-xs text-gray-500">
        {opt.context || opt.tier} {opt.cost}
      </span>
    </button>
  );
}

export function ScreenModelSelector({ screen, className = "" }: ScreenModelSelectorProps) {
  const [current, setCurrent] = useState<ScreenModelInfo | undefined>();
  const [models, setModels] = useState<AiModelOption[]>([]);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [canEdit, setCanEdit] = useState(false);
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const [config, catalog] = await Promise.all([
        api.getAiConfigForScreens(),
        api.listAiModels(),
      ]);
      setCurrent(config.screen_models.find((s) => s.screen === screen));
      setModels(catalog.models);
      setCanEdit(true);
    } catch {
      try {
        const config = await api.getAiConfig();
        setCurrent(config.screen_models.find((s) => s.screen === screen));
        setModels([
          ...config.paid_model_options.map((m) => ({ ...m, group: "premium" as const })),
          ...config.low_cost_model_options.map((m) => ({ ...m, group: "low_cost" as const })),
          ...config.free_model_options.map((m) => ({ ...m, group: "free" as const })),
        ]);
        setCanEdit(true);
      } catch {
        setCurrent(undefined);
        setModels([]);
        setCanEdit(false);
      }
    }
  }, [screen]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return models;
    return models.filter(
      (m) =>
        m.label.toLowerCase().includes(q) ||
        m.provider.toLowerCase().includes(q) ||
        m.model.toLowerCase().includes(q),
    );
  }, [models, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, AiModelOption[]>();
    for (const section of GROUP_SECTIONS) {
      const items = filtered.filter((m) => m.group === section.key);
      if (items.length > 0) map.set(section.key, items);
    }
    return map;
  }, [filtered]);

  async function selectModel(provider: string, model: string) {
    setSaving(true);
    try {
      await api.setScreenModelOverride(screen, provider, model);
      await load();
      setOpen(false);
    } catch {
      /* read-only users cannot save */
    } finally {
      setSaving(false);
    }
  }

  async function clearOverride() {
    setSaving(true);
    try {
      await api.setScreenModelOverride(screen, null, null);
      await load();
      setOpen(false);
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  }

  if (!current) return null;

  const isOverride = current.source === "override";
  const displayLabel = isOverride ? current.label : "Auto";

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      <div className="flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-900/80 px-3 py-1.5 text-sm">
        <span>{displayLabel}</span>
        {canEdit ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            disabled={saving}
            className="rounded px-2 py-0.5 text-xs text-gray-400 hover:bg-gray-800 hover:text-white"
          >
            ▾ Change
          </button>
        ) : null}
      </div>

      {open ? (
        <div className="absolute right-0 z-50 mt-2 flex max-h-[32rem] w-96 flex-col rounded-xl border border-gray-700 bg-gray-950 shadow-xl">
          <div className="border-b border-gray-800 p-3">
            <p className="mb-2 text-xs font-medium text-gray-400">
              Model for this screen ({models.length} total)
            </p>
            <input
              type="search"
              placeholder="Search models…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-md border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm"
            />
          </div>

          <div className="overflow-y-auto p-3">
            <button
              type="button"
              onClick={() => void clearOverride()}
              className={`mb-3 flex w-full items-center rounded-md px-2 py-1.5 text-left text-sm hover:bg-gray-900 ${
                !isOverride ? "bg-gray-900 ring-1 ring-blue-600" : ""
              }`}
            >
              {!isOverride ? "●" : "○"} Auto (tier routing chain)
            </button>

            <div className="mb-2 border-t border-gray-800" />

            {GROUP_SECTIONS.map((section) => {
              const opts = grouped.get(section.key) ?? [];
              if (opts.length === 0) return null;
              return (
                <div key={section.key} className="mb-3">
                  <p
                    className={`mb-1 text-xs font-semibold uppercase tracking-wide ${section.colorClass}`}
                  >
                    {section.label} ({opts.length})
                  </p>
                  {opts.map((opt) => {
                    const selected =
                      isOverride &&
                      current.provider === opt.provider &&
                      current.model === opt.model;
                    return (
                      <ModelOptionButton
                        key={`${section.key}-${opt.provider}-${opt.model}`}
                        opt={opt}
                        selected={selected}
                        onSelect={() => void selectModel(opt.provider, opt.model)}
                      />
                    );
                  })}
                </div>
              );
            })}

            {filtered.length === 0 ? (
              <p className="py-4 text-center text-sm text-gray-500">No models match</p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function stars(count: number): string {
  return "⭐".repeat(Math.min(5, Math.max(1, count)));
}

export function QualityStars({ count }: { count: number }) {
  return <span title={`${count}/5`}>{stars(count)}</span>;
}
