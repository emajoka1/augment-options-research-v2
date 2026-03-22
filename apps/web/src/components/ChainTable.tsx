export function ChainTable({ rows }: { rows: { strike: number; iv: number; expiry: number | null }[] }) {
  return (
    <div className="overflow-hidden rounded-3xl border border-white/70 bg-white/70 shadow-[0_12px_30px_rgba(15,23,42,0.05)]">
      <table className="min-w-full divide-y divide-zinc-200 text-sm">
        <thead className="bg-zinc-50/80 text-left text-zinc-500">
          <tr>
            <th className="px-4 py-3 font-semibold">Strike</th>
            <th className="px-4 py-3 font-semibold">IV</th>
            <th className="px-4 py-3 font-semibold">Expiry (days)</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white/80">
          {rows.map((row) => (
            <tr key={row.strike} className="hover:bg-zinc-50/80">
              <td className="px-4 py-3 font-semibold text-zinc-900">{row.strike}</td>
              <td className="px-4 py-3 text-zinc-700">{(row.iv * 100).toFixed(1)}%</td>
              <td className="px-4 py-3 text-zinc-700">{row.expiry ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
