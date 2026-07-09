/** Route-transition skeleton for all studio screens — no more blank flashes. */
export default function StudioLoading() {
  return (
    <div className="animate-pulse space-y-6 p-1" aria-busy="true" aria-label="Loading">
      <div className="space-y-2">
        <div className="h-3 w-24 rounded bg-gray-800" />
        <div className="h-7 w-64 rounded bg-gray-800" />
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 rounded-xl border border-gray-800 bg-gray-900/50" />
        ))}
      </div>
      <div className="h-64 rounded-xl border border-gray-800 bg-gray-900/50" />
      <div className="h-40 rounded-xl border border-gray-800 bg-gray-900/50" />
    </div>
  );
}
