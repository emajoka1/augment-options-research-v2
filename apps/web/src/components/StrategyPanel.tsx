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
    <aside className="space-y-6 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
      <div>
        <p className="text-sm uppercase tracking-[0.2em] text-zinc-500">Strategy Builder</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">Configure structure</h2>
      </div>
      <div className="space-y-4">
        <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-700">Strategy type</span><select value={strategyType} onChange={(e) => onChangeStrategyType(e.target.value)} className="w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm"><option value="iron_fly">Iron fly</option><option value="iron_condor">Iron condor</option><option value="long_straddle">Long straddle</option></select></label>
        <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-700">Model</span><select value={model} onChange={(e) => onChangeModel(e.target.value)} className="w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm"><option value="jump">Jump diffusion</option><option value="gbm">GBM</option><option value="heston">Heston</option></select></label>
        <label className="block text-sm font-medium text-zinc-700">Spread bps: {spreadBps}<input type="range" min={5} max={60} value={spreadBps} onChange={(e) => onChangeSpreadBps(Number(e.target.value))} className="mt-2 w-full" /></label>
        <label className="block text-sm font-medium text-zinc-700">Slippage bps: {slippageBps}<input type="range" min={1} max={20} value={slippageBps} onChange={(e) => onChangeSlippageBps(Number(e.target.value))} className="mt-2 w-full" /></label>
      </div>
      <div className="rounded-2xl bg-zinc-50 p-4 text-sm text-zinc-600">Running config: {strategyType} · {model} · spot {spot}</div>
      <div className="rounded-2xl border border-zinc-200 p-4">
        <div className="flex items-center justify-between gap-2"><p className="text-sm font-semibold text-zinc-900">Strategy analysis</p><button onClick={onAnalyze} className="rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-50">{loadingStrategy ? 'Analyzing…' : 'Analyze'}</button></div>
        <div className="mt-4 space-y-3 text-sm text-zinc-700">
          <div className="grid grid-cols-2 gap-3"><MetricCard label="Entry" value={strategyResult?.entry_value} /><MetricCard label="Max Profit" value={strategyResult?.max_profit} /><MetricCard label="Max Loss" value={strategyResult?.max_loss} /><MetricCard label="Breakevens" value={strategyResult?.breakevens?.[0]} /></div>
          <div><p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Configured legs</p><div className="mt-2 flex flex-wrap gap-2">{strategyLegs.map((leg, idx) => <span key={idx} className="rounded-full bg-zinc-50 px-3 py-1 text-xs font-medium text-zinc-600 ring-1 ring-zinc-200">{leg.side} {leg.option_type} {leg.strike}</span>)}</div></div>
          <button onClick={onRunMc} className="w-full rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700">Run MC on this strategy</button>
        </div>
      </div>
      <div className="rounded-2xl border border-zinc-200 p-4">
        {running ? <div className="space-y-2"><p className="font-medium text-zinc-900">Running 20 × 2,000 paths…</p><div className="h-2 overflow-hidden rounded-full bg-zinc-200"><div className="h-full w-2/3 animate-pulse rounded-full bg-zinc-900" /></div></div> : mcResult ? <div className="space-y-4"><div><p className="text-xs uppercase tracking-[0.2em] text-zinc-500">MC Result</p><p className="mt-1 text-lg font-semibold text-zinc-900">{mcResult.status}</p></div><div className="grid grid-cols-3 gap-3 text-sm"><MetricCard label="EV" value={mcResult.metrics?.ev} /><MetricCard label="POP" value={mcResult.metrics?.pop} /><MetricCard label="CVaR" value={mcResult.metrics?.cvar95} /></div><div><p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Gates</p><div className="mt-2 flex flex-wrap gap-2">{Object.entries(mcResult.gates ?? {}).map(([key, value]) => <span key={key} className={`rounded-full px-3 py-1 text-xs font-medium ${value === true ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-100 text-zinc-700'}`}>{key}</span>)}</div></div></div> : <p className="text-sm text-zinc-500">Analyze a strategy or run MC to see results here.</p>}
      </div>
    </aside>
  )
}
