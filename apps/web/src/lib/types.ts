export type ChainResponse = { symbol: string; spot: number; strikes: number[]; ivs: number[]; expiry_days: number[] | null; source: string }
export type MCResponse = { status: string; metrics?: { ev?: number; pop?: number; cvar95?: number }; gates?: Record<string, boolean | number | string | null>; edge_attribution?: Record<string, string | number | boolean | null> }
export type BriefCandidate = { type?: string; decision?: string; gateFailures?: string[]; score?: { Total?: number } }
export type BriefResponse = { 'TRADE BRIEF'?: { Ticker?: string; Spot?: number | null; ['Final Decision']?: string; NoCandidatesReason?: string | null; missingRequiredData?: string[]; Candidates?: BriefCandidate[] } }
export type StrategyAnalyzeResponse = { entry_value: number; breakevens: number[] | null; max_profit: number; max_loss: number; greeks_aggregate: { delta: number; gamma: number; vega: number; theta_daily: number } }
export type VolSurfaceResponse = { symbol: string; iv_atm: number; skew: number; curv: number; strikes: number[]; ivs: number[]; fitted_ivs: number[] }
export type StrategyLeg = { side: string; option_type: string; strike: number; qty: number; expiry_years: number }
