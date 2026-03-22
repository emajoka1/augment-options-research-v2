import type { ChainResponse } from './types'

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8787'

export const demoChain: ChainResponse = {
  symbol: 'SPY',
  spot: 600,
  strikes: [585, 590, 595, 600, 605, 610, 615],
  ivs: [0.23, 0.235, 0.242, 0.25, 0.255, 0.261, 0.268],
  expiry_days: [7, 7, 7, 7, 7, 7, 7],
  source: 'demo-placeholder',
}
