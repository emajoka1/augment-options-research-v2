'use client'

import { useEffect, useMemo, useState } from 'react'

type ChainResponse = {
  symbol: string
  spot: number
  strikes: number[]
  ivs: number[]
  expiry_days: number[] | null
  source: string
}

type MCResponse = {
  status: string
  metrics?: { ev?: number; pop?: number; cvar95?: number }
  gates?: Record<string, boolean | number | string | null>
  edge_attribution?: Record<string, string | number | boolean | null>
}

type BriefCandidate = {
  type?: string
  decision?: string
  gateFailures?: string[]
  score?: { Total?: number }
}

type BriefResponse = {
  'TRADE BRIEF'?: {
    Ticker?: string
    Spot?: number | null
    ['Final Decision']?: string
    NoCandidatesReason?: string | null
    missingRequiredData?: string[]
    Candidates?: BriefCandidate[]
  }
}

type StrategyAnalyzeResponse = {
  entry_value: number
  breakevens: number[] | null
  max_profit: number
  max_loss: number
  greeks_aggregate: { delta: number; gamma: number; vega: number; theta_daily: number }
}

const demoChain: ChainResponse = {
  symbol: 'SPY',
  spot: 600,
  strikes: [585, 590, 595, 600, 605, 610, 615],
  ivs: [0.23, 0.235, 0.242, 0.25, 0.255, 0.261, 0.268],
  expiry_days: [7, 7, 7, 7, 7, 7, 7],
  source: 'demo',
}

const demoMc: MCResponse = {
  status: 'FULL_REFRESH',
  metrics: { ev: 0.82, pop: 0.61, cvar95: -1.14 },
  gates: { allow_trade: true, ev_gate: true, cvar_gate: true, pop_or_pot: true },
  edge_attribution: { explainable: true, iv_rich_vs_rv: 0.04 },
}

const demoBrief: BriefResponse = {
  'TRADE BRIEF': {
    Ticker: 'SPY',
    Spot: 600,
    'Final Decision': 'TRADE',
    NoCandidatesReason: null,
    missingRequiredData: [],
    Candidates: [
      { type: 'debit', decision: 'TRADE', gateFailures: [], score: { Total: 78 } },
      { type: 'condor', decision: 'PASS', gateFailures: ['execution_poor'], score: { Total: 63 } },
    ],
  },
}

const demoStrategy: StrategyAnalyzeResponse = {
  entry_value: -2.4,
  breakevens: [597.6, 602.4],
  max_profit: 2.6,
  max_loss: -2.4,
  greeks_aggregate: { delta: 0, gamma: 0, vega: 0, theta_daily: 0 },
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8787'

export default function Home() {
  const [chain, setChain] = useState<ChainResponse>(demoChain)
  const [mcResult, setMcResult] = useState<MCResponse | null>(null)
  const [briefResult, setBriefResult] = useState<BriefResponse | null>(demoBrief)
  const [strategyResult, setStrategyResult] = useState<StrategyAnalyzeResponse | null>(demoStrategy)
  const [running, setRunning] = useState(false)
  const [loadingChain, setLoadingChain] = useState(false)
  const [loadingBrief, setLoadingBrief] = useState(false)
  const [loadingStrategy, setLoadingStrategy] = useState(false)
  const [statusMessage, setStatusMessage] = useState('Using demo market data until the local API stack is available.')
  const [strategyType, setStrategyType] = useState('iron_fly')
  const [model, setModel] = useState('jump')
  const [spreadBps, setSpreadBps] = useState(30)
  const [slippageBps, setSlippageBps] = useState(8)

  useEffect(() => {
    let cancelled = false
    const loadChain = async () => {
      setLoadingChain(true)
      try {
        const response = await fetch(`${API_BASE}/api/v1/chain/SPY?snapshot_path=${encodeURIComponent('/tmp/demo-chain.json')}`)
        if (!response.ok) throw new Error('chain request failed')
        const payload = (await response.json()) as ChainResponse
        if (!cancelled) {
          setChain(payload)
          setStatusMessage(`Live chain loaded from ${payload.source}.`)
        }
      } catch {
        if (!cancelled) {
          setChain(demoChain)
          setStatusMessage('Using demo market data until the local API stack is available.')
        }
      } finally {
        if (!cancelled) setLoadingChain(false)
      }
    }
    void loadChain()
    return () => {
      cancelled = true
    }
  }, [])

  const rows = useMemo(() => chain.strikes.map((strike, idx) => ({ strike, iv: chain.ivs[idx], expiry: chain.expiry_days?.[idx] ?? null })), [chain])

  const strategyLegs = useMemo(() => {
    const center = chain.spot
    switch (strategyType) {
      case 'iron_condor':
        return [
          { side: 'short', option_type: 'put', strike: center - 5, qty: 1, expiry_years: 0.0137 },
          { side: 'long', option_type: 'put', strike: center - 10, qty: 1, expiry_years: 0.0137 },
          { side: 'short', option_type: 'call', strike: center + 5, qty: 1, expiry_years: 0.0137 },
          { side: 'long', option_type: 'call', strike: center + 10, qty: 1, expiry_years: 0.0137 },
        ]
      case 'long_straddle':
        return [
          { side: 'long', option_type: 'call', strike: center, qty: 1, expiry_years: 0.0137 },
          { side: 'long', option_type: 'put', strike: center, qty: 1, expiry_years: 0.0137 },
        ]
      default:
        return [
          { side: 'short', option_type: 'call', strike: center, qty: 1, expiry_years: 0.0137 },
          { side: 'short', option_type: 'put', strike: center, qty: 1, expiry_years: 0.0137 },
          { side: 'long', option_type: 'call', strike: center + 10, qty: 1, expiry_years: 0.0137 },
          { side: 'long', option_type: 'put', strike: center - 10, qty: 1, expiry_years: 0.0137 },
        ]
    }
  }, [chain.spot, strategyType])

  const runMc = async () => {
    setRunning(true)
    setMcResult(null)
    try {
      const response = await fetch(`${API_BASE}/api/v1/mc/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: chain.symbol, spot: chain.spot, strategy_type: strategyType, model, spread_bps: spreadBps, slippage_bps: slippageBps, n_batches: 1, paths_per_batch: 100, expiry_days: chain.expiry_days?.[0] ?? 7, dt_days: 1, write_artifacts: false }),
      })
      if (!response.ok) throw new Error('mc request failed')
      setMcResult((await response.json()) as MCResponse)
      setStatusMessage('Monte Carlo result loaded from research engine.')
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500))
      setMcResult({ ...demoMc, metrics: { ...demoMc.metrics, ev: Number((0.7 + spreadBps / 200).toFixed(2)) } })
      setStatusMessage('Using demo Monte Carlo output until the local API stack is available.')
    } finally {
      setRunning(false)
    }
  }

  const loadBrief = async () => {
    setLoadingBrief(true)
    try {
      const response = await fetch(`${API_BASE}/api/v1/brief/${chain.symbol}`, { method: 'POST' })
      if (!response.ok) throw new Error('brief request failed')
      setBriefResult((await response.json()) as BriefResponse)
      setStatusMessage('Trade brief loaded from research engine.')
    } catch {
      setBriefResult(demoBrief)
      setStatusMessage('Using demo trade brief until the local API stack is available.')
    } finally {
      setLoadingBrief(false)
    }
  }

  const analyzeStrategy = async () => {
    setLoadingStrategy(true)
    try {
      const response = await fetch(`${API_BASE}/api/v1/strategy/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ legs: strategyLegs, spot: chain.spot, r: 0.03, q: 0 }),
      })
      if (!response.ok) throw new Error('strategy request failed')
      setStrategyResult((await response.json()) as StrategyAnalyzeResponse)
      setStatusMessage('Strategy analysis loaded from research engine.')
    } catch {
      setStrategyResult(demoStrategy)
      setStatusMessage('Using demo strategy analysis until the local API stack is available.')
    } finally {
      setLoadingStrategy(false)
    }
  }

  const brief = briefResult?.['TRADE BRIEF']

  return (
    <main className="min-h-screen bg-zinc-50 p-8 text-zinc-900">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 rounded-2xl border border-zinc-200 bg-white px-5 py-4 text-sm text-zinc-600 shadow-sm">{loadingChain ? 'Loading chain…' : statusMessage}</div>

        <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <section className="space-y-6 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm uppercase tracking-[0.2em] text-zinc-500">Chain Viewer</p>
                <h1 className="mt-2 text-3xl font-semibold tracking-tight">{chain.symbol} options chain</h1>
                <p className="mt-2 text-sm text-zinc-600">Spot {chain.spot} · Source {chain.source}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={loadBrief} className="rounded-xl border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-50">{loadingBrief ? 'Loading brief…' : 'Load brief'}</button>
                <button onClick={runMc} className="rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700">Run MC</button>
              </div>
            </div>

            <div className="overflow-hidden rounded-2xl border border-zinc-200">
              <table className="min-w-full divide-y divide-zinc-200 text-sm">
                <thead className="bg-zinc-50 text-left text-zinc-500"><tr><th className="px-4 py-3 font-medium">Strike</th><th className="px-4 py-3 font-medium">IV</th><th className="px-4 py-3 font-medium">Expiry (days)</th></tr></thead>
                <tbody className="divide-y divide-zinc-100 bg-white">{rows.map((row) => <tr key={row.strike}><td className="px-4 py-3 font-medium">{row.strike}</td><td className="px-4 py-3">{(row.iv * 100).toFixed(1)}%</td><td className="px-4 py-3">{row.expiry ?? '—'}</td></tr>)}</tbody>
              </table>
            </div>

            <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between gap-3"><div><p className="text-sm uppercase tracking-[0.2em] text-zinc-500">Trade brief</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">{brief?.Ticker ?? chain.symbol} brief</h2></div><span className="rounded-full bg-zinc-100 px-3 py-1 text-sm font-medium text-zinc-700">{brief?.['Final Decision'] ?? 'NO TRADE'}</span></div>
              <div className="mt-4 grid gap-4 md:grid-cols-[1fr_1fr]"><div className="rounded-2xl bg-zinc-50 p-4"><p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Missing required data</p><div className="mt-3 flex flex-wrap gap-2">{(brief?.missingRequiredData?.length ? brief.missingRequiredData : ['none']).map((item) => <span key={item} className="rounded-full bg-white px-3 py-1 text-xs font-medium text-zinc-700 ring-1 ring-zinc-200">{item}</span>)}</div></div><div className="rounded-2xl bg-zinc-50 p-4"><p className="text-xs uppercase tracking-[0.2em] text-zinc-500">No-candidate reason</p><p className="mt-3 text-sm text-zinc-700">{brief?.NoCandidatesReason ?? 'Candidates available.'}</p></div></div>
              <div className="mt-4 space-y-3">{(brief?.Candidates ?? []).map((candidate, idx) => <div key={`${candidate.type}-${idx}`} className="rounded-2xl border border-zinc-200 p-4"><div className="flex items-center justify-between gap-3"><div><p className="text-sm font-semibold text-zinc-900">{candidate.type ?? 'candidate'}</p><p className="text-xs text-zinc-500">Decision {candidate.decision ?? 'PASS'}</p></div><span className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-700">Score {candidate.score?.Total ?? '—'}</span></div><div className="mt-3 flex flex-wrap gap-2">{(candidate.gateFailures?.length ? candidate.gateFailures : ['clean']).map((gate) => <span key={gate} className="rounded-full bg-zinc-50 px-3 py-1 text-xs font-medium text-zinc-600 ring-1 ring-zinc-200">{gate}</span>)}</div></div>)}</div>
            </div>
          </section>

          <aside className="space-y-6 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
            <div>
              <p className="text-sm uppercase tracking-[0.2em] text-zinc-500">Strategy Builder</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight">Configure structure</h2>
            </div>

            <div className="space-y-4">
              <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-700">Strategy type</span><select value={strategyType} onChange={(e) => setStrategyType(e.target.value)} className="w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm"><option value="iron_fly">Iron fly</option><option value="iron_condor">Iron condor</option><option value="long_straddle">Long straddle</option></select></label>
              <label className="block"><span className="mb-2 block text-sm font-medium text-zinc-700">Model</span><select value={model} onChange={(e) => setModel(e.target.value)} className="w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm"><option value="jump">Jump diffusion</option><option value="gbm">GBM</option><option value="heston">Heston</option></select></label>
              <label className="block text-sm font-medium text-zinc-700">Spread bps: {spreadBps}<input type="range" min={5} max={60} value={spreadBps} onChange={(e) => setSpreadBps(Number(e.target.value))} className="mt-2 w-full" /></label>
              <label className="block text-sm font-medium text-zinc-700">Slippage bps: {slippageBps}<input type="range" min={1} max={20} value={slippageBps} onChange={(e) => setSlippageBps(Number(e.target.value))} className="mt-2 w-full" /></label>
            </div>

            <div className="rounded-2xl bg-zinc-50 p-4 text-sm text-zinc-600">Running config: {strategyType} · {model} · spot {chain.spot}</div>

            <div className="rounded-2xl border border-zinc-200 p-4">
              <div className="flex items-center justify-between gap-2"><p className="text-sm font-semibold text-zinc-900">Strategy analysis</p><button onClick={analyzeStrategy} className="rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-50">{loadingStrategy ? 'Analyzing…' : 'Analyze'}</button></div>
              <div className="mt-4 space-y-3 text-sm text-zinc-700">
                <div className="grid grid-cols-2 gap-3"><MetricCard label="Entry" value={strategyResult?.entry_value} /><MetricCard label="Max Profit" value={strategyResult?.max_profit} /><MetricCard label="Max Loss" value={strategyResult?.max_loss} /><MetricCard label="Breakevens" value={strategyResult?.breakevens?.[0]} /></div>
                <div><p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Configured legs</p><div className="mt-2 flex flex-wrap gap-2">{strategyLegs.map((leg, idx) => <span key={idx} className="rounded-full bg-zinc-50 px-3 py-1 text-xs font-medium text-zinc-600 ring-1 ring-zinc-200">{leg.side} {leg.option_type} {leg.strike}</span>)}</div></div>
                <button onClick={runMc} className="w-full rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700">Run MC on this strategy</button>
              </div>
            </div>

            <div className="rounded-2xl border border-zinc-200 p-4">
              {running ? <div className="space-y-2"><p className="font-medium text-zinc-900">Running 20 × 2,000 paths…</p><div className="h-2 overflow-hidden rounded-full bg-zinc-200"><div className="h-full w-2/3 animate-pulse rounded-full bg-zinc-900" /></div></div> : mcResult ? <div className="space-y-4"><div><p className="text-xs uppercase tracking-[0.2em] text-zinc-500">MC Result</p><p className="mt-1 text-lg font-semibold text-zinc-900">{mcResult.status}</p></div><div className="grid grid-cols-3 gap-3 text-sm"><MetricCard label="EV" value={mcResult.metrics?.ev} /><MetricCard label="POP" value={mcResult.metrics?.pop} /><MetricCard label="CVaR" value={mcResult.metrics?.cvar95} /></div><div><p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Gates</p><div className="mt-2 flex flex-wrap gap-2">{Object.entries(mcResult.gates ?? {}).map(([key, value]) => <span key={key} className={`rounded-full px-3 py-1 text-xs font-medium ${value === true ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-100 text-zinc-700'}`}>{key}</span>)}</div></div></div> : <p className="text-sm text-zinc-500">Analyze a strategy or run MC to see results here.</p>}
            </div>
          </aside>
        </div>
      </div>
    </main>
  )
}

function MetricCard({ label, value }: { label: string; value: number | undefined }) {
  return <div className="rounded-2xl border border-zinc-200 bg-white p-3"><p className="text-xs uppercase tracking-[0.2em] text-zinc-500">{label}</p><p className="mt-2 text-lg font-semibold text-zinc-900">{typeof value === 'number' ? value.toFixed(2) : '—'}</p></div>
}
