import { MetricCard } from './MetricCard'
import type { VolSurfaceResponse } from '../lib/types'

export function VolSurfacePanel({ symbol, surface }: { symbol: string; surface: VolSurfaceResponse | null }) {
  if (!surface) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <p className="text-sm uppercase tracking-[0.2em] text-zinc-500">Vol surface</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">{symbol} surface</h2>
        <p className="mt-4 text-sm text-zinc-500">No surface loaded yet. Use “Load surface” to fetch fitted volatility data.</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-zinc-500">Vol surface</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight">{surface.symbol ?? symbol} surface</h2>
        </div>
        <span className="rounded-full bg-zinc-100 px-3 py-1 text-sm font-medium text-zinc-700">ATM IV {surface.iv_atm.toFixed(2)}</span>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <MetricCard label="Skew" value={surface.skew} />
        <MetricCard label="Curvature" value={surface.curv} />
        <MetricCard label="Points" value={surface.strikes.length} />
      </div>
      <div className="mt-4 space-y-2">
        {surface.strikes.map((strike, idx) => (
          <div key={strike} className="grid grid-cols-[80px_1fr_80px] items-center gap-3 text-sm">
            <span className="text-zinc-600">{strike}</span>
            <div className="h-2 rounded-full bg-zinc-100">
              <div className="h-2 rounded-full bg-zinc-900" style={{ width: `${Math.min(100, (surface.fitted_ivs[idx] ?? 0) * 250)}%` }} />
            </div>
            <span className="text-right text-zinc-500">{((surface.fitted_ivs[idx] ?? 0) * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
