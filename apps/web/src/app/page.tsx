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
    backendAvailable,
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
    <main className="min-h-screen px-4 py-8 text-zinc-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-zinc-500">Augment Options Research</p>
            <h1 className="mt-3 text-4xl font-semibold tracking-tight text-zinc-950 sm:text-5xl">Research cockpit</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-600">
              Explore chain structure, generate trade briefs, inspect fitted volatility, and run Monte Carlo from one tidy surface.
            </p>
          </div>
          <div className={`rounded-2xl border px-5 py-4 text-sm shadow-sm ${backendAvailable ? 'border-emerald-200 bg-emerald-50/90 text-emerald-800' : 'border-amber-200 bg-amber-50/90 text-amber-900'}`}>
            {loadingChain ? 'Loading chain…' : statusMessage}
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.45fr_0.95fr]">
          <section className="space-y-6 rounded-3xl border border-white/70 bg-white/80 p-6 shadow-[0_20px_50px_rgba(15,23,42,0.08)] backdrop-blur-sm">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-500">Chain Viewer</p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-950">{chain.symbol} options chain</h2>
                <p className="mt-2 text-sm text-zinc-600">Spot {chain.spot} · Source {chain.source}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button onClick={loadBrief} className="rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-sm font-medium text-zinc-900 shadow-sm hover:bg-zinc-50">{loadingBrief ? 'Loading brief…' : 'Load brief'}</button>
                <button onClick={loadSurface} className="rounded-xl border border-zinc-300 bg-white px-4 py-2.5 text-sm font-medium text-zinc-900 shadow-sm hover:bg-zinc-50">{loadingSurface ? 'Loading surface…' : 'Load surface'}</button>
                <button onClick={runMc} className="rounded-xl bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-zinc-900/10 hover:bg-zinc-800">Run MC</button>
              </div>
            </div>

            {!backendAvailable && (
              <div className="rounded-2xl border border-dashed border-amber-300 bg-amber-50/90 p-4 text-sm leading-6 text-amber-900">
                The backend is currently unavailable. Values shown below are visual placeholders, not live research output.
              </div>
            )}

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
