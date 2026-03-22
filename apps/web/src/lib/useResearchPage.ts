import { useEffect, useMemo, useState } from 'react'
import { API_BASE, demoBrief, demoChain, demoStrategy, demoSurface } from './demo-data'
import type { BriefResponse, ChainResponse, MCResponse, StrategyAnalyzeResponse, StrategyLeg, VolSurfaceResponse } from './types'

export function useResearchPage() {
  const [chain, setChain] = useState<ChainResponse>(demoChain)
  const [mcResult, setMcResult] = useState<MCResponse | null>(null)
  const [briefResult, setBriefResult] = useState<BriefResponse | null>(null)
  const [strategyResult, setStrategyResult] = useState<StrategyAnalyzeResponse | null>(null)
  const [surfaceResult, setSurfaceResult] = useState<VolSurfaceResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [loadingChain, setLoadingChain] = useState(false)
  const [loadingBrief, setLoadingBrief] = useState(false)
  const [loadingStrategy, setLoadingStrategy] = useState(false)
  const [loadingSurface, setLoadingSurface] = useState(false)
  const [statusMessage, setStatusMessage] = useState('Waiting for the local API stack. Demo values are shown as placeholders only.')
  const [backendAvailable, setBackendAvailable] = useState(false)
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
          setBackendAvailable(true)
          setStatusMessage(`Live chain loaded from ${payload.source}.`)
        }
      } catch {
        if (!cancelled) {
          setChain(demoChain)
          setBackendAvailable(false)
          setStatusMessage('Backend unavailable. Demo chain is visible only as a placeholder.')
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
  const strategyLegs = useMemo<StrategyLeg[]>(() => {
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
      setMcResult(null)
      setStatusMessage('Monte Carlo request failed. Start the local API stack to run simulations.')
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
      setStatusMessage('Trade brief unavailable. Demo brief is shown as a placeholder.')
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
      setStrategyResult(null)
      setStatusMessage('Strategy analysis unavailable. Start the local API stack to analyze configured legs.')
    } finally {
      setLoadingStrategy(false)
    }
  }

  const loadSurface = async () => {
    setLoadingSurface(true)
    try {
      const response = await fetch(`${API_BASE}/api/v1/vol-surface/${chain.symbol}?snapshot_path=${encodeURIComponent('/tmp/demo-chain.json')}`)
      if (!response.ok) throw new Error('surface request failed')
      setSurfaceResult((await response.json()) as VolSurfaceResponse)
      setStatusMessage('Vol surface loaded from research engine.')
    } catch {
      setSurfaceResult(null)
      setStatusMessage('Vol surface unavailable. Start the local API stack to fetch fitted volatility data.')
    } finally {
      setLoadingSurface(false)
    }
  }

  return {
    chain, mcResult, briefResult, strategyResult, surfaceResult,
    running, loadingChain, loadingBrief, loadingStrategy, loadingSurface,
    statusMessage, backendAvailable, strategyType, model, spreadBps, slippageBps,
    setStrategyType, setModel, setSpreadBps, setSlippageBps,
    rows, strategyLegs, runMc, loadBrief, analyzeStrategy, loadSurface,
  }
}
