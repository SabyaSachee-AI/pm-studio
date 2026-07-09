"use client";

/** Last-resort boundary — catches crashes in the root layout itself.
 * Must render its own <html>/<body> because the layout is gone. */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en" className="dark h-full">
      <body className="flex min-h-full items-center justify-center bg-gray-950 font-sans text-gray-200 antialiased">
        <div className="w-full max-w-md rounded-xl border border-red-900/50 bg-red-950/20 p-6 text-center">
          <h2 className="text-lg font-semibold">PM Studio hit a fatal error</h2>
          <p className="mt-1.5 text-sm text-gray-400">
            Reload the app — if this keeps happening, check the browser console.
          </p>
          {error?.message ? (
            <p className="mt-3 rounded bg-gray-900/70 px-3 py-2 text-left font-mono text-xs text-red-300">
              {error.message.slice(0, 300)}
            </p>
          ) : null}
          <button
            onClick={() => reset()}
            className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
