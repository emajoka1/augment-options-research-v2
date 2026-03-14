# RESULT: options_mc_data_quality_fail_dedupe_circuit_breaker

## Summary
Implemented a data-quality fail dedupe circuit breaker in `scripts/ak_options_mc.py`.

### What changed
- Added new CLI flags:
  - `--force-refresh` (manual bypass)
  - `--dq-fail-dedupe-cooldown-minutes` (default 30)
- Added DQ-fail dedupe behavior:
  - If canonical inputs are unchanged, same `data_quality_status` persists, and cooldown not elapsed:
    - Return compact payload with `status=NO_ACTION_DQ_FAIL_DUPLICATE`
    - Include: `generated_at`, `status`, `data_quality_status`, `dedupe_window_seconds`, `prior_artifact`
    - Skip full regeneration
- Added bypass conditions:
  - DQ status transition forces full refresh once
  - Canonical hash change already bypasses dedupe
  - Cooldown expiry forces full refresh and increments republish telemetry
  - Manual `--force-refresh` bypasses dedupe
- Added telemetry counters in full refresh payload:
  - `options_mc_runs_dq_fail_deduped` (0 on full refresh)
  - `options_mc_runs_dq_fail_republished_after_cooldown` (1 when applicable)

## Files changed
- `scripts/ak_options_mc.py`
- `tests/test_options_mc_idempotent_artifact_guard.py`
- `tests/test_options_mc_dq_fail_dedupe_circuit_breaker.py` (new)

## Test evidence
- Targeted tests:
  - `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_options_mc_idempotent_artifact_guard.py tests/test_options_mc_dq_fail_dedupe_circuit_breaker.py`
  - Result: `7 passed`
- Full suite (required):
  - `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
  - Result: `63 passed`

## Commit
- `54e8a5a2bf2c4eea70eb56eb80eb5cdb4e5cc8ad`
