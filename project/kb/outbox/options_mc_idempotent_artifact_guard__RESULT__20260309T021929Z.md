# RESULT: options_mc_idempotent_artifact_guard

- Ticket: /Users/forge/.openclaw/workspace/kb/inbox/AUTO_IMPROVE__options_mc_idempotent_artifact_guard__20260309T0205Z.json
- Branch: ticket/options_mc_idempotent_artifact_guard
- Commit: 51c77b5c6de98fb13e252d11de80fc4c40dfeaec

## What changed
- Added canonical-input idempotency guard in `scripts/ak_options_mc.py` using `canonical_inputs` + `canonical_inputs_hash`.
- Added machine-readable skip response when inputs unchanged within cadence:
  - `status: NO_NEW_INPUTS`
  - `prior_artifact` reference (path/generated_at/config_hash/canonical_inputs_hash)
  - telemetry block with `options_mc_runs_skipped_no_new_inputs`.
- Added recalc cadence override via CLI:
  - `--force-refresh-minutes` (default 30)
  - when cadence elapsed with unchanged inputs, full run proceeds and telemetry increments `options_mc_runs_forced_refresh`.
- Added telemetry counters on full artifacts:
  - `options_mc_runs_total`
  - `options_mc_runs_skipped_no_new_inputs`
  - `options_mc_runs_forced_refresh`
- Added artifact fields:
  - `status: FULL_REFRESH`
  - `canonical_inputs`
  - `canonical_inputs_hash`
- Added tests in `tests/test_options_mc_idempotent_artifact_guard.py` for:
  - unchanged inputs skip behavior
  - changed canonical input full artifact generation
  - forced refresh cadence behavior + telemetry

## Proof
- Full test suite command:
  - `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Result:
  - `57 passed`
