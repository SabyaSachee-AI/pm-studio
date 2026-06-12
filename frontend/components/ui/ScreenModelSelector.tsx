"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AiConfigResponse, type AiModelOption, type ScreenModelInfo } from "@/lib/api";

type ScreenKey = "requirements" | "prds" | "srs" | "architecture" | "tasks";

interface ScreenModelSelectorProps {
  screen: ScreenKey;
  className?: string;
}

const GROUP_SECTIONS: Array<{
  key: "paid" | "low_cost" | "free";
  label: string;
  colorClass: string;
  icon: string;
  optionsKey: keyof Pick<
    AiConfigResponse,
    "paid_model_options" | "low_cost_model_options" | "free_model_options"
  >;
}> = [
  {
    key: "paid",
    label: "Paid",
    colorClass: "text-orange-400",
    icon: "🟠",
    optionsKey: "paid_model_options",
  },
  {
    key: "low_cost",
    label: "Low cost",
    colorClass: "text-amber-400",
    icon: "💰",
    optionsKey: "low_cost_model_options",
  },
  {
    key: "free",
    label: "Free",
    colorClass: "text-green-400",
    icon: "🆓",
    optionsKey: "free_model_options",
  },
];

function stars(count: number): string {
  return "⭐".repeat(Math.min(5, Math.max(1, count)));
}

function ModelOptionButton({
  opt,
  selected,
  icon,
  onSelect,
}: {
  opt: AiModelOption;
  selected: boolean;
  icon: string;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`mb-1 flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-gray-900 ${
        selected ? "bg-gray-900 ring-1 ring-blue-600" : ""
      }`}
    >
      <span>
        {selected ? "●" : "○"} {icon} {opt.label}
      </span>
      <span className="text-xs text-gray-500">
        {opt.tier} {opt.cost}
      </span>
    </button>
  );
}

export function ScreenModelSelector({ screen, className = "" }: ScreenModelSelectorProps) {
  const [config, setConfig] = useState<AiConfigResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [canEdit, setCanEdit] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.getAiConfigForScreens();
      setConfig(data);
      setCanEdit(true);
    } catch {
      try {
        const data = await api.getAiConfig();
        setConfig(data);
        setCanEdit(true);
      } catch {
        setConfig(null);
        setCanEdit(false);
      }
    }
  }, []);

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

  const current: ScreenModelInfo | undefined = config?.screen_models.find(
    (s) => s.screen === screen,
  );

  async function selectModel(provider: string, model: string) {
    setSaving(true);
    try {
      const updated = await api.setScreenModelOverride(screen, provider, model);
      setConfig(updated);
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
      const updated = await api.setScreenModelOverride(screen, null, null);
      setConfig(updated);
      setOpen(false);
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  }

  if (!config || !current) return null;

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
        <div className="absolute right-0 z-50 mt-2 max-h-[28rem] w-80 overflow-y-auto rounded-xl border border-gray-700 bg-gray-950 p-3 shadow-xl">
          <p className="mb-2 text-xs font-medium text-gray-400">
            Model for this screen
          </p>

          <button
            type="button"
            onClick={() => void clearOverride()}
            className={`mb-3 flex w-full items-center rounded-md px-2 py-1.5 text-left text-sm hover:bg-gray-900 ${
              !isOverride ? "bg-gray-900 ring-1 ring-blue-600" : ""
            }`}
          >
            {!isOverride ? "●" : "○"} Auto
          </button>

          <div className="mb-2 border-t border-gray-800" />

          {GROUP_SECTIONS.map((section) => {
            const opts = config[section.optionsKey] ?? [];
            if (opts.length === 0) return null;
            return (
              <div key={section.key} className="mb-3">
                <p
                  className={`mb-1 text-xs font-semibold uppercase tracking-wide ${section.colorClass}`}
                >
                  {section.label}
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
                      icon={section.icon}
                      onSelect={() => void selectModel(opt.provider, opt.model)}
                    />
                  );
                })}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export function QualityStars({ count }: { count: number }) {
  return <span title={`${count}/5`}>{stars(count)}</span>;
}
