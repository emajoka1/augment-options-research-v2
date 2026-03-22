# RESULT — AUTO_IMPROVE__options_mc_breakeven_null_regression_contract__20260309T0639Z

## Summary
Implemented a fail-closed breakeven contract path so unsolved breakevens are surfaced as explicit typed failures, not silent null-driven explainability degradation.

### What changed
- `scripts/ak_options_mc.py`
  - Added typed failure code mapping: `BREAKEVEN_SOLVER_FAIL:<reason>` when solver cannot produce breakevens.
  - `edge_attribution.structure_expected_move_match` is now `None` (not misleading `0.0`) when breakevens are unavailable.
  - Explainability now requires solved breakevens; unsolved solver path sets explicit `explainable_reason` with the typed failure code.
  - Payload now publishes typed failure in `breakeven_reason`.
- `src/ak_system/mc_options/report.py`
  - Markdown rendering now prints explicit failure reason instead of `Breakevens: None`.
- Added test suite: `tests/test_options_mc_breakeven_null_regression_contract.py`
  - Supported vertical/diagonal structures emit non-empty numeric breakevens.
  - Unsolved path emits typed failure code and disables explainability with explicit reason.
  - Markdown contract never prints `Breakevens: None`.

## Validation / Proof
- Full suite (required):
  - `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
  - Result: **pass**

## Commit
- `871d3c885eae145c06586d2560664922e7bc2d68`
