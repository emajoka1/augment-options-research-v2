import { MetricCard } from './MetricCard'
import type { VolSurfaceResponse } from '../lib/types'

export function VolSurfacePanel({ symbol, surface }: { symbol: string; surface: VolSurfaceResponse | null }) {
  if (!surface) {
    return (
      <div className="rounded-3xl border border-white/70 bg-white/80 p-6 shadow-[0_20px_50px_rgba(15,23,42,0.08)] backdrop-blur-sm">
        <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-500">Vol surface</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-950">{symbol} surface</h2>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-zinc-600">No surface loaded yet. Pull fitted volatility data to inspect ATM IV, skew, and curvature across strikes.</p>
      </div>
    )
  }

  return (
    <div className="rounded-3xl border border-white/70 bg-white/80 p-6 shadow-[0_20px_50px_rgba(15,23,42,0.08)] backdrop-blur-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-500">Vol surface</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-950">{surface.symbol ?? symbol} surface</h2>
        </div>
        <span className="rounded-full border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-semibold text-sky-700">ATM IV {surface.iv_atm.toFixed(2)}</span>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-3">
        <MetricCard label="Skew" value={surface.skew} />
        <MetricCard label="Curvature" value={surface.curv} />
        <MetricCard label="Points" value={surface.strikes.length} />
      </div>
      <div className="mt-5 space-y-3 rounded-2xl border border-zinc-200/70 bg-zinc-50/60 p-4">
        {surface.strikes.map((strike, idx) => (
          <div key={strike} className="grid grid-cols-[80px_1fr_80px] items-center gap-3 text-sm">
            <span className="font-medium text-zinc-700">{strike}</span>
            <div className="h-2.5 rounded-full bg-zinc-200/80">
              <div className="h-2.5 rounded-full bg-gradient-to-r from-sky-500 to-indigo-500" style={{ width: `${Math.min(100, (surface.fitted_ivs[idx] ?? 0) * 250)}%` }} />
            </div>
            <span className="text-right text-zinc-500">{((surface.fitted_ivs[idx] ?? 0) * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
