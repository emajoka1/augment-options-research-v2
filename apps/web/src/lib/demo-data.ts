import type { BriefResponse, ChainResponse, MCResponse, StrategyAnalyzeResponse, VolSurfaceResponse } from './types'

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8787'

export const demoChain: ChainResponse = { symbol: 'SPY', spot: 600, strikes: [585, 590, 595, 600, 605, 610, 615], ivs: [0.23, 0.235, 0.242, 0.25, 0.255, 0.261, 0.268], expiry_days: [7, 7, 7, 7, 7, 7, 7], source: 'demo' }
export const demoMc: MCResponse = { status: 'FULL_REFRESH', metrics: { ev: 0.82, pop: 0.61, cvar95: -1.14 }, gates: { allow_trade: true, ev_gate: true, cvar_gate: true, pop_or_pot: true }, edge_attribution: { explainable: true, iv_rich_vs_rv: 0.04 } }
export const demoBrief: BriefResponse = { 'TRADE BRIEF': { Ticker: 'SPY', Spot: 600, 'Final Decision': 'TRADE', NoCandidatesReason: null, missingRequiredData: [], Candidates: [{ type: 'debit', decision: 'TRADE', gateFailures: [], score: { Total: 78 } }, { type: 'condor', decision: 'PASS', gateFailures: ['execution_poor'], score: { Total: 63 } }] } }
export const demoStrategy: StrategyAnalyzeResponse = { entry_value: -2.4, breakevens: [597.6, 602.4], max_profit: 2.6, max_loss: -2.4, greeks_aggregate: { delta: 0, gamma: 0, vega: 0, theta_daily: 0 } }
export const demoSurface: VolSurfaceResponse = { symbol: 'SPY', iv_atm: 0.25, skew: -0.12, curv: 0.34, strikes: [585, 590, 595, 600, 605, 610, 615], ivs: [0.23, 0.235, 0.242, 0.25, 0.255, 0.261, 0.268], fitted_ivs: [0.232, 0.236, 0.242, 0.25, 0.256, 0.262, 0.267] }
