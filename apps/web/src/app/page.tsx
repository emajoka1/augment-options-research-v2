'use client'

import { BriefPanel } from '../components/BriefPanel'
import { ChainTable } from '../components/ChainTable'
import { StrategyPanel } from '../components/StrategyPanel'
import { VolSurfacePanel } from '../components/VolSurfacePanel'
import { useResearchPage } from '../lib/useResearchPage'

export default function Home() {
  const {
    chain,
    mcResult,
    briefResult,
    strategyResult,
    surfaceResult,
    running,
    loadingChain,
    loadingBrief,
    loadingStrategy,
    loadingSurface,
    statusMessage,
    strategyType,
    model,
    spreadBps,
    slippageBps,
    setStrategyType,
    setModel,
    setSpreadBps,
    setSlippageBps,
    rows,
    strategyLegs,
    runMc,
    loadBrief,
    analyzeStrategy,
    loadSurface,
  } = useResearchPage()

  return (
    <main className="min-h-screen bg-zinc-50 p-8 text-zinc-900">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 rounded-2xl border border-zinc-200 bg-white px-5 py-4 text-sm text-zinc-600 shadow-sm">
          {loadingChain ? 'Loading chain…' : statusMessage}
        </div>

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
                <button onClick={loadSurface} className="rounded-xl border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-zinc-50">{loadingSurface ? 'Loading surface…' : 'Load surface'}</button>
                <button onClick={runMc} className="rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700">Run MC</button>
              </div>
            </div>

            <ChainTable rows={rows} />
            <BriefPanel symbol={chain.symbol} brief={briefResult?.['TRADE BRIEF']} />
            <VolSurfacePanel symbol={chain.symbol} surface={surfaceResult} />
          </section>

          <StrategyPanel
            strategyType={strategyType}
            model={model}
            spreadBps={spreadBps}
            slippageBps={slippageBps}
            loadingStrategy={loadingStrategy}
            running={running}
            strategyResult={strategyResult}
            mcResult={mcResult}
            strategyLegs={strategyLegs}
            onChangeStrategyType={setStrategyType}
            onChangeModel={setModel}
            onChangeSpreadBps={setSpreadBps}
            onChangeSlippageBps={setSlippageBps}
            onAnalyze={analyzeStrategy}
            onRunMc={runMc}
            spot={chain.spot}
          />
        </div>
      </div>
    </main>
  )
}
