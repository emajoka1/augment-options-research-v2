export function ChainTable({ rows }: { rows: { strike: number; iv: number; expiry: number | null }[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200">
      <table className="min-w-full divide-y divide-zinc-200 text-sm">
        <thead className="bg-zinc-50 text-left text-zinc-500">
          <tr>
            <th className="px-4 py-3 font-medium">Strike</th>
            <th className="px-4 py-3 font-medium">IV</th>
            <th className="px-4 py-3 font-medium">Expiry (days)</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 bg-white">
          {rows.map((row) => (
            <tr key={row.strike}>
              <td className="px-4 py-3 font-medium">{row.strike}</td>
              <td className="px-4 py-3">{(row.iv * 100).toFixed(1)}%</td>
              <td className="px-4 py-3">{row.expiry ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
