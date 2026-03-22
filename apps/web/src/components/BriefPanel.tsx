import type { BriefResponse } from '../lib/types'

export function BriefPanel({ symbol, brief }: { symbol: string; brief: BriefResponse['TRADE BRIEF'] | undefined }) {
  if (!brief) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <p className="text-sm uppercase tracking-[0.2em] text-zinc-500">Trade brief</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">{symbol} brief</h2>
        <p className="mt-4 text-sm text-zinc-500">No brief loaded yet. Use “Load brief” to fetch one from the research engine.</p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-zinc-500">Trade brief</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight">{brief.Ticker ?? symbol} brief</h2>
        </div>
        <span className="rounded-full bg-zinc-100 px-3 py-1 text-sm font-medium text-zinc-700">{brief['Final Decision'] ?? 'NO TRADE'}</span>
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-[1fr_1fr]">
        <div className="rounded-2xl bg-zinc-50 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Missing required data</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(brief.missingRequiredData?.length ? brief.missingRequiredData : ['none']).map((item) => (
              <span key={item} className="rounded-full bg-white px-3 py-1 text-xs font-medium text-zinc-700 ring-1 ring-zinc-200">{item}</span>
            ))}
          </div>
        </div>
        <div className="rounded-2xl bg-zinc-50 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">No-candidate reason</p>
          <p className="mt-3 text-sm text-zinc-700">{brief.NoCandidatesReason ?? 'Candidates available.'}</p>
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {(brief.Candidates ?? []).map((candidate, idx) => (
          <div key={`${candidate.type}-${idx}`} className="rounded-2xl border border-zinc-200 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-zinc-900">{candidate.type ?? 'candidate'}</p>
                <p className="text-xs text-zinc-500">Decision {candidate.decision ?? 'PASS'}</p>
              </div>
              <span className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-700">Score {candidate.score?.Total ?? '—'}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {(candidate.gateFailures?.length ? candidate.gateFailures : ['clean']).map((gate) => (
                <span key={gate} className="rounded-full bg-zinc-50 px-3 py-1 text-xs font-medium text-zinc-600 ring-1 ring-zinc-200">{gate}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
