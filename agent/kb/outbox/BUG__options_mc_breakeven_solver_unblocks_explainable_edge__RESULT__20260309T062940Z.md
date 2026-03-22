# RESULT — BUG__options_mc_breakeven_solver_unblocks_explainable_edge

## Summary
Implemented acceptance coverage to prevent silent breakeven suppression paths and enforce explainability coupling:
- Added integration contract test ensuring solved breakevens propagate into non-zero `structure_expected_move_match` and `edge_attribution.explainable=true` when gates are otherwise satisfiable.
- Added regression test over the most recent 20 `kb/experiments/options-mc-*.json` artifacts to guarantee no `breakevens: []` emissions.

## Files changed
- `tests/test_options_mc_breakeven_contract.py` (new)

## Test evidence
Executed:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_options_mc_breakeven_contract.py`
  - Result: `2 passed`
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
  - Result: `51 passed`

## Commit
- `b0b0a64`
