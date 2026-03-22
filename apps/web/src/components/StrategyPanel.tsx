import { MetricCard } from './MetricCard'
import type { MCResponse, StrategyAnalyzeResponse, StrategyLeg } from '../lib/types'

export function StrategyPanel(props: {
  strategyType: string
  model: string
  spreadBps: number
  slippageBps: number
  loadingStrategy: boolean
  running: boolean
  strategyResult: StrategyAnalyzeResponse | null
  mcResult: MCResponse | null
  strategyLegs: StrategyLeg[]
  onChangeStrategyType: (v: string) => void
  onChangeModel: (v: string) => void
  onChangeSpreadBps: (v: number) => void
  onChangeSlippageBps: (v: number) => void
  onAnalyze: () => void
  onRunMc: () => void
  spot: number
}) {
  const { strategyType, model, spreadBps, slippageBps, loadingStrategy, running, strategyResult, mcResult, strategyLegs, onChangeStrategyType, onChangeModel, onChangeSpreadBps, onChangeSlippageBps, onAnalyze, onRunMc, spot } = props
  return (
    <aside className="space-y-6 rounded-3xl border border-white/70 bg-white/80 p-6 shadow-[0_20px_50px_rgba(15,23,42,0.08)] backdrop-blur-sm">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-500">Strategy Builder</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-950">Configure structure</h2>
      </div>
      <div className="space-y-4 rounded-2xl border border-zinc-200/70 bg-zinc-50/70 p-4">
        <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-700">Strategy type</span><select value={strategyType} onChange={(e) => onChangeStrategyType(e.target.value)} className="w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-sm shadow-sm"><option value="iron_fly">Iron fly</option><option value="iron_condor">Iron condor</option><option value="long_straddle">Long straddle</option></select></label>
        <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-700">Model</span><select value={model} onChange={(e) => onChangeModel(e.target.value)} className="w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-sm shadow-sm"><option value="jump">Jump diffusion</option><option value="gbm">GBM</option><option value="heston">Heston</option></select></label>
        <label className="block text-sm font-medium text-zinc-700">Spread bps: {spreadBps}<input type="range" min={5} max={60} value={spreadBps} onChange={(e) => onChangeSpreadBps(Number(e.target.value))} className="mt-2 w-full accent-zinc-900" /></label>
        <label className="block text-sm font-medium text-zinc-700">Slippage bps: {slippageBps}<input type="range" min={1} max={20} value={slippageBps} onChange={(e) => onChangeSlippageBps(Number(e.target.value))} className="mt-2 w-full accent-zinc-900" /></label>
      </div>
      <div className="rounded-2xl border border-indigo-100 bg-gradient-to-r from-indigo-50 to-sky-50 p-4 text-sm font-medium text-indigo-900">Running config: {strategyType} · {model} · spot {spot}</div>
      <div className="rounded-2xl border border-zinc-200/70 bg-white p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
        <div className="flex items-center justify-between gap-2"><p className="text-sm font-semibold text-zinc-950">Strategy analysis</p><button onClick={onAnalyze} className="rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-900 shadow-sm hover:bg-zinc-50">{loadingStrategy ? 'Analyzing…' : 'Analyze'}</button></div>
        <div className="mt-4 space-y-3 text-sm text-zinc-700">
          {strategyResult ? (
            <div className="grid grid-cols-2 gap-3"><MetricCard label="Entry" value={strategyResult.entry_value} /><MetricCard label="Max Profit" value={strategyResult.max_profit} /><MetricCard label="Max Loss" value={strategyResult.max_loss} /><MetricCard label="Breakevens" value={strategyResult.breakevens?.[0]} /></div>
          ) : (
            <p className="rounded-2xl border border-dashed border-zinc-300 bg-zinc-50 p-4 text-sm text-zinc-500">No strategy analysis yet. Click “Analyze” to price the configured legs.</p>
          )}
          <div><p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">Configured legs</p><div className="mt-2 flex flex-wrap gap-2">{strategyLegs.map((leg, idx) => <span key={idx} className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-medium text-zinc-700 shadow-sm">{leg.side} {leg.option_type} {leg.strike}</span>)}</div></div>
          <button onClick={onRunMc} className="w-full rounded-xl bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-zinc-900/10 hover:bg-zinc-800">Run MC on this strategy</button>
        </div>
      </div>
      <div className="rounded-2xl border border-zinc-200/70 bg-white p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
        {running ? <div className="space-y-3"><p className="font-medium text-zinc-900">Running 20 × 2,000 paths…</p><div className="h-2.5 overflow-hidden rounded-full bg-zinc-200"><div className="h-full w-2/3 animate-pulse rounded-full bg-gradient-to-r from-emerald-500 to-sky-500" /></div></div> : mcResult ? <div className="space-y-4"><div><p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">MC Result</p><p className="mt-1 text-lg font-semibold text-zinc-950">{mcResult.status}</p></div><div className="grid grid-cols-3 gap-3 text-sm"><MetricCard label="EV" value={mcResult.metrics?.ev} /><MetricCard label="POP" value={mcResult.metrics?.pop} /><MetricCard label="CVaR" value={mcResult.metrics?.cvar95} /></div><div><p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">Gates</p><div className="mt-2 flex flex-wrap gap-2">{Object.entries(mcResult.gates ?? {}).map(([key, value]) => <span key={key} className={`rounded-full px-3 py-1 text-xs font-semibold ${value === true ? 'border border-emerald-200 bg-emerald-50 text-emerald-700' : 'border border-zinc-200 bg-zinc-50 text-zinc-700'}`}>{key}</span>)}</div></div></div> : <p className="rounded-2xl border border-dashed border-zinc-300 bg-zinc-50 p-4 text-sm text-zinc-500">No MC result yet. Run a simulation to see EV, POP, CVaR, and gate status.</p>}
      </div>
    </aside>
  )
}
