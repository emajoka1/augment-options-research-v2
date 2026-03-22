# RESULT — options_mc_breakeven_solver_unblocks_explainable_edge

## Summary
Implemented robust, deterministic breakeven solving from terminal payoff with explicit failure reasons (no empty-list fallback), wired artifact fields for breakeven reason/solver diagnostics, and added tests for put diagonal and undefined/non-crossing paths.

## Branch
`ticket/options_mc_breakeven_solver_unblocks_explainable_edge`

## Commit
`2d90017`

## Files changed
- `src/ak_system/mc_options/strategy.py`
- `scripts/ak_options_mc.py`
- `tests/test_options_mc.py`

## Proof (tests)
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_options_mc.py tests/test_options_mc_provenance_contract.py` ✅
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q` ✅ (exit code 0)

## Contract checks
- Multi-leg breakeven solving now uses bracketed root search over deterministic spot grid.
- Undefined breakeven paths now emit `breakevens: null` + `breakeven_reason` (never `[]`).
- `structure_expected_move_match` now uses solved breakevens when present, explicit undefined path otherwise.
- Added solver diagnostics (`breakeven_solver`) for fail-loud telemetry.
