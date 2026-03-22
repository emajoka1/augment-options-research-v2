export function MetricCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-2xl border border-white/70 bg-white/80 p-4 shadow-[0_10px_30px_rgba(15,23,42,0.06)] backdrop-blur-sm">
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">{label}</p>
      <p className="mt-2 text-xl font-semibold tracking-tight text-zinc-950">{typeof value === 'number' ? value.toFixed(2) : '—'}</p>
    </div>
  )
}
