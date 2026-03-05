- Ticket id: `riskcap_first_candidate_generation`

## Summary
Implemented risk-cap-first candidate generation in `scripts/spy_free_brief.py` so infeasible structures are filtered **before** selection/ranking. This prevents non-executable candidates from being surfaced as top structures under strict caps (e.g., `$75`).

## What was broken
- Candidate generation for debit/credit/condor could fall back to non-viable pools when no feasible legs passed cap/liquidity checks.
- Condor pairing could retain infeasible combinations with only a score penalty.
- This allowed non-executable candidates to enter later ranking/diagnostic flow.

## What changed
### `scripts/spy_free_brief.py`
- Added `risk_cap_dollars()` helper (single source of truth for cap).
- Updated generation gates to use cap helper consistently.
- **Debit spread** generation: removed fallback to unfiltered pool; now selects only viable short leg.
- **Credit spread** generation: removed fallback to unfiltered pool; now selects only viable long leg.
- **Condor** generation: infeasible combinations are now skipped (`continue`) and never selected.
- Updated downstream hard gate and risk framework output to use `risk_cap_dollars()`.

### `tests/test_spy_free_brief_riskcap.py` (new)
- `test_riskcap_first_generation_enforces_cap_pre_selection`
  - Sets `MAX_RISK_DOLLARS=75` and asserts returned executable candidates satisfy cap.
- `test_no_candidates_message_exact_and_diagnostics_present`
  - Forces cap too low and asserts exact no-candidates string:
    - `NO_CANDIDATES: risk_cap too low for this DTE/structure under current IV/spreads.`
  - Asserts diagnostics shape remains present (3 candidates + closest near miss flip hint).

## Tests run + output
1. Focused ticket tests:
   - Command: `./.venv/bin/python -m pytest -q tests/test_spy_free_brief_riskcap.py`
   - Result: `2 passed`

2. Full suite per workflow:
   - Command: `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
   - Result: `2 failed, 24 passed`
   - Existing unrelated failures in `tests/test_mc_command.py`:
     - `test_normalize_partial_data_forces_no_trade`
     - `test_normalize_trade_ready_when_clean`

## Files changed
- `scripts/spy_free_brief.py`
- `tests/test_spy_free_brief_riskcap.py`

## New config flags
- None added.
- Existing risk cap config (`SPY_MAX_RISK_DOLLARS`) now applied consistently through `risk_cap_dollars()`.

## Commit hash
- `42ae785`

## Risk of behavioural drift
- Low: changes are constrained to candidate feasibility gating and consistent cap evaluation.
- Intentional effect: fewer/no candidates under tight caps; system fails closed with exact NO_CANDIDATES messaging.
