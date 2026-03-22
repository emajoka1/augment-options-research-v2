# Autonomous Research + Knowledge System

## Overview

This system separates research from production execution:

- **RESEARCH_AGENT**: can collect, distill, validate, and propose changes.
- **PRODUCTION_AGENT**: read-only consumer of approved playbooks/rules. Cannot self-modify.

## Directory layout

- `kb/sources/` raw collected source indexes
- `kb/summaries/` distilled notes and knowledge items
- `kb/concepts/` schemas and conceptual docs
- `kb/playbooks/` executable human-readable playbooks
- `kb/rules/` machine-readable scoring/risk rules
- `kb/experiments/` validation reports
- `kb/decisions/approved|pending|rejected/` governance states
- `kb/trade_logs/` trade journals and replay inputs
- `experiments/` sandbox data (e.g., `trades.csv`)
- `proposals/` generated CHANGE_PROPOSAL artifacts
- `snapshots/` rollback snapshots for kb/

## Core loops

1. **Collect**: ingest new sources + trade logs
2. **Distill**: produce structured knowledge candidates (with claim/evidence/confidence)
3. **Validate**: run metrics + baseline comparison + Monte Carlo stress
4. **Propose**: create proposal artifacts with rollback plan
5. **Promote**: manual approval only, then move into approved decisions

## Validation requirements

Each proposed rule must pass:
- Unit tests
- Backtest/replay inputs
- Monte Carlo stress (`vol_expansion`, `gap_down`, `gap_up`)
- A/B vs baseline comparator

Tracked metrics:
- `win_rate`
- `avg_r`
- `max_drawdown`
- `tail_loss`
- `slippage_sensitivity`

If sample size is insufficient, report is labeled `UNVERIFIED` and proposal cannot be promoted.

## Running

From workspace root:

```bash
PYTHONPATH=src python3 scripts/ak_scheduler.py --mode once
PYTHONPATH=src python3 scripts/ak_scheduler.py --mode daemon
PYTHONPATH=src python3 scripts/ak_regime_harness.py --paths 500
PYTHONPATH=src python3 scripts/ak_framework.py --paths 600 --seed 42
```

The regime harness writes JSON + markdown reports to `kb/experiments/` and auto-creates a proposal in `proposals/` when improvements are detected.

The full framework run performs out-of-sample validation and automated scorecard weight recalibration (proposal-only; no direct production mutation).

## Approval flow

1. Generate proposals via scheduler.
2. Review JSON/MD in `proposals/`.
3. Approve/reject manually:

```bash
PYTHONPATH=src python3 scripts/ak_admin.py approve proposals/<file>.json --approver "<name>"
PYTHONPATH=src python3 scripts/ak_admin.py reject proposals/<file>.json --reason "<reason>"
```

Approved copies are written to:
- `kb/decisions/pending/` (audit trail)
- `kb/decisions/approved/` (active governance)

## Rollback

Every approval creates a snapshot in `snapshots/kb-<timestamp>/`.
Rollback to latest snapshot:

```bash
PYTHONPATH=src python3 scripts/ak_admin.py rollback
```

## Audit checklist

- Verify proposal status and approver metadata.
- Confirm tests passed and sample size threshold met.
- Confirm out-of-sample delta and stress outcomes.
- Ensure rollback plan exists.
- Ensure production consumes only approved files.
