"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";

interface GeneratedDocActionsProps {
  editHref?: string;
  editLabel?: string;
  onDelete: () => Promise<void>;
  onRegenerate?: () => Promise<void>;
  showEdit?: boolean;
  showRegenerate?: boolean;
  showDelete?: boolean;
  className?: string;
}

export function GeneratedDocActions({
  editHref,
  editLabel = "Edit",
  onDelete,
  onRegenerate,
  showEdit = true,
  showRegenerate = true,
  showDelete = true,
  className = "",
}: GeneratedDocActionsProps) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
      setOpen(false);
    }
  }

  return (
    <div className={`relative ${className}`}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={() => setOpen((v) => !v)}
      >
        Actions ▾
      </Button>
      {open ? (
        <div className="absolute right-0 z-50 mt-1 min-w-[10rem] rounded-lg border border-gray-700 bg-gray-950 py-1 shadow-xl">
          {showEdit && editHref ? (
            <Link
              href={editHref}
              className="block px-3 py-2 text-sm text-gray-200 hover:bg-gray-900"
              onClick={() => setOpen(false)}
            >
              ✏️ {editLabel}
            </Link>
          ) : null}
          {showRegenerate && onRegenerate ? (
            <button
              type="button"
              className="block w-full px-3 py-2 text-left text-sm text-gray-200 hover:bg-gray-900"
              disabled={busy}
              onClick={() => run(onRegenerate)}
            >
              🔄 Regenerate
            </button>
          ) : null}
          {showDelete ? (
            <button
              type="button"
              className="block w-full px-3 py-2 text-left text-sm text-red-300 hover:bg-gray-900"
              disabled={busy}
              onClick={() => {
                if (window.confirm("Delete this document? This cannot be undone.")) {
                  void run(onDelete);
                }
              }}
            >
              🗑 Delete
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
