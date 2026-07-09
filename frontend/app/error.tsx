"use client";

import { useEffect } from "react";

/** Route-level error boundary — a component crash shows this instead of a
 * white screen, and "Try again" re-renders the segment without losing the app. */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface the real error for debugging without crashing the UI.
    console.error("Route error boundary caught:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="w-full max-w-md rounded-xl border border-red-900/50 bg-red-950/20 p-6 text-center">
        <i className="ti ti-alert-triangle text-3xl text-red-400" aria-hidden />
        <h2 className="mt-3 text-lg font-semibold text-gray-100">
          Something went wrong on this screen
        </h2>
        <p className="mt-1.5 text-sm text-gray-400">
          The rest of PM Studio is fine — this screen hit an unexpected error.
          Your data is safe.
        </p>
        {error?.message ? (
          <p className="mt-3 rounded bg-gray-900/70 px-3 py-2 text-left font-mono text-xs text-red-300">
            {error.message.slice(0, 300)}
          </p>
        ) : null}
        <div className="mt-4 flex justify-center gap-2">
          <button
            onClick={() => reset()}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-500"
          >
            Try again
          </button>
          <button
            onClick={() => (window.location.href = "/dashboard")}
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 transition hover:bg-gray-800"
          >
            Go to dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
