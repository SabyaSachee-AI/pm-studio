"use client";

import { useEffect } from "react";

export type ToastType = "success" | "error" | "info";

type ToastProps = {
  message: string;
  type?: ToastType;
  visible: boolean;
  onDismiss: () => void;
  autoDismissMs?: number;
};

export function Toast({
  message,
  type = "success",
  visible,
  onDismiss,
  autoDismissMs = 4000,
}: ToastProps) {
  useEffect(() => {
    if (!visible) return;
    const id = window.setTimeout(onDismiss, autoDismissMs);
    return () => clearTimeout(id);
  }, [visible, message, onDismiss, autoDismissMs]);

  if (!visible || !message) return null;

  const styles =
    type === "success"
      ? "border-green-700 bg-green-900 text-green-100"
      : type === "error"
        ? "border-red-700 bg-red-900 text-red-100"
        : "border-blue-700 bg-blue-900 text-blue-100";

  return (
    <div
      className={`fixed right-4 top-4 z-[100] max-w-sm rounded-lg border px-4 py-3 text-sm shadow-lg ${styles}`}
      role="status"
      aria-live="polite"
    >
      {message}
    </div>
  );
}
