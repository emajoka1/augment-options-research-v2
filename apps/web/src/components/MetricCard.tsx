export function MetricCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-3">
      <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">{label}</p>
      <p className="mt-2 text-lg font-semibold text-zinc-900">{typeof value === 'number' ? value.toFixed(2) : '—'}</p>
    </div>
  )
}
