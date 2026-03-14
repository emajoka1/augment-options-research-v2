- Ticket id: `stack_phase1_akshare_qlib_adapter`

## Ticket summary
Implemented research-only Phase-1 AKShare + Qlib adapters with unified schema and artifact output to `kb/experiments/stack-phase1-*.json`, without modifying execution gates.

## Changes made
- Added unified adapter schema and validator:
  - `src/ak_system/adapters/common.py`
- Added AKShare adapter (optional dependency, fail-closed quality flags):
  - `src/ak_system/adapters/akshare_adapter.py`
- Added Qlib adapter (optional dependency, research-only factor placeholders):
  - `src/ak_system/adapters/qlib_adapter.py`
- Added adapter exports:
  - `src/ak_system/adapters/__init__.py`
- Added phase1 orchestrator + artifact writer:
  - `src/ak_system/stack/phase1.py`
  - `scripts/stack_phase1_run.py`
- Added tests for schema contract and non-null timestamps:
  - `tests/test_stack_phase1_adapters.py`

## Files changed
- `src/ak_system/adapters/common.py`
- `src/ak_system/adapters/akshare_adapter.py`
- `src/ak_system/adapters/qlib_adapter.py`
- `src/ak_system/adapters/__init__.py`
- `src/ak_system/stack/phase1.py`
- `scripts/stack_phase1_run.py`
- `tests/test_stack_phase1_adapters.py`

## Commands run + proof
1) Affected tests:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_stack_phase1_adapters.py`
- Output: `.. [100%]`

2) Full suite:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Output: `...................................... [100%]`

3) Manual phase artifact proof:
- `PYTHONPATH=src ./.venv/bin/python scripts/stack_phase1_run.py`
- Produced: `kb/experiments/stack-phase1-20260305-203424.json`
- Evidence: `phase=stack_phase1`, `research_only=True`, adapters include `akshare`, `qlib`.

4) Manual `mc_command --json` schema diff note (phase boundary):
- `python3 scripts/mc_command.py --max-attempts 1 --retry-delay-sec 1 --json`
- Checked required keys still present:
  - `trace_ids=True`
  - `spot_integrity=True`
  - `mc_provenance=True`
  - `trade_ready_rule=True`
- Breaking schema diff: **none**.

## Risks / follow-ups
- Optional external dependencies (`akshare`, `qlib`) may be unavailable; adapters explicitly mark this via quality flags and stay research-only.
- No execution-path or trade-gate logic modified.

## Commit hash
- 
