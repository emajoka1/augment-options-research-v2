import type { BriefResponse } from '../lib/types'

export function BriefPanel({ symbol, brief }: { symbol: string; brief: BriefResponse['TRADE BRIEF'] | undefined }) {
  if (!brief) {
    return (
      <div className="rounded-3xl border border-white/70 bg-white/80 p-6 shadow-[0_20px_50px_rgba(15,23,42,0.08)] backdrop-blur-sm">
        <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-500">Trade brief</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-950">{symbol} brief</h2>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-zinc-600">No brief loaded yet. Pull one from the research engine to see candidate structures, final decision, and gate failures.</p>
      </div>
    )
  }

  return (
    <div className="rounded-3xl border border-white/70 bg-white/80 p-6 shadow-[0_20px_50px_rgba(15,23,42,0.08)] backdrop-blur-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-500">Trade brief</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-950">{brief.Ticker ?? symbol} brief</h2>
        </div>
        <span className="rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700">{brief['Final Decision'] ?? 'NO TRADE'}</span>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-[1fr_1fr]">
        <div className="rounded-2xl border border-zinc-200/70 bg-zinc-50/80 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">Missing required data</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(brief.missingRequiredData?.length ? brief.missingRequiredData : ['none']).map((item) => (
              <span key={item} className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-medium text-zinc-700">{item}</span>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-zinc-200/70 bg-zinc-50/80 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500">No-candidate reason</p>
          <p className="mt-3 text-sm leading-6 text-zinc-700">{brief.NoCandidatesReason ?? 'Candidates available.'}</p>
        </div>
      </div>
      <div className="mt-5 space-y-3">
        {(brief.Candidates ?? []).map((candidate, idx) => (
          <div key={`${candidate.type}-${idx}`} className="rounded-2xl border border-zinc-200/70 bg-white p-4 shadow-[0_8px_24px_rgba(15,23,42,0.04)]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-zinc-950">{candidate.type ?? 'candidate'}</p>
                <p className="text-xs text-zinc-500">Decision {candidate.decision ?? 'PASS'}</p>
              </div>
              <span className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-700">Score {candidate.score?.Total ?? '—'}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {(candidate.gateFailures?.length ? candidate.gateFailures : ['clean']).map((gate) => (
                <span key={gate} className="rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-medium text-zinc-600">{gate}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
