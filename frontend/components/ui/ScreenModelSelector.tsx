"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AiConfigResponse, type ScreenModelInfo } from "@/lib/api";

type ScreenKey = "requirements" | "prds" | "srs" | "architecture" | "tasks";

interface ScreenModelSelectorProps {
  screen: ScreenKey;
  className?: string;
}

function stars(count: number): string {
  return "⭐".repeat(Math.min(5, Math.max(1, count)));
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

  const isFree = config.free_mode_enabled || current.model.includes(":free");
  const icon = isFree ? "🆓" : "🤖";
  const options = config.free_mode_enabled
    ? config.free_model_options
    : [...config.paid_model_options, ...config.free_model_options];

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      <div className="flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-900/80 px-3 py-1.5 text-sm">
        <span>
          {icon} {current.label}
        </span>
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
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-xl border border-gray-700 bg-gray-950 p-3 shadow-xl">
          <p className="mb-2 text-xs font-medium text-gray-400">
            Model for this screen (overrides global setting)
          </p>
          <div className="mb-2 border-t border-gray-800" />

          {!config.free_mode_enabled ? (
            <>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-orange-400">
                Paid models
              </p>
              {config.paid_model_options.map((opt) => {
                const selected =
                  current.provider === opt.provider && current.model === opt.model;
                return (
                  <button
                    key={`${opt.provider}-${opt.model}`}
                    type="button"
                    onClick={() => selectModel(opt.provider, opt.model)}
                    className={`mb-1 flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-gray-900 ${
                      selected ? "bg-gray-900 ring-1 ring-orange-600" : ""
                    }`}
                  >
                    <span>
                      {selected ? "●" : "○"} 🟠 {opt.label}
                    </span>
                    <span className="text-xs text-gray-500">
                      {opt.tier} {opt.cost}
                    </span>
                  </button>
                );
              })}
              <p className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide text-blue-400">
                Free models (OpenRouter)
              </p>
            </>
          ) : (
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-green-400">
              Free models
            </p>
          )}

          {(config.free_mode_enabled ? config.free_model_options : config.free_model_options).map(
            (opt) => {
              const selected =
                current.provider === opt.provider && current.model === opt.model;
              return (
                <button
                  key={`free-${opt.provider}-${opt.model}`}
                  type="button"
                  onClick={() => selectModel(opt.provider, opt.model)}
                  className={`mb-1 flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-gray-900 ${
                    selected ? "bg-gray-900 ring-1 ring-green-600" : ""
                  }`}
                >
                  <span>
                    {selected ? "●" : "○"} 🆓 {opt.label}
                  </span>
                  <span className="text-xs text-gray-500">{opt.tier}</span>
                </button>
              );
            },
          )}

          {current.source === "override" ? (
            <button
              type="button"
              onClick={clearOverride}
              className="mt-2 w-full rounded-md border border-gray-700 px-2 py-1.5 text-xs text-gray-400 hover:bg-gray-900"
            >
              Use global default
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function QualityStars({ count }: { count: number }) {
  return <span title={`${count}/5`}>{stars(count)}</span>;
}
