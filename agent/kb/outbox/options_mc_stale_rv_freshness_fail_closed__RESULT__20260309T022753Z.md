# RESULT: options_mc_stale_rv_freshness_fail_closed

## Summary
Implemented fail-closed RV freshness SLA handling in `scripts/ak_options_mc.py`.

### What changed
- Added CLI flag `--rv-freshness-sla-seconds` (default `3600`).
- Added explicit RV freshness evaluation fields to every artifact:
  - `rv_freshness_sla_seconds`
  - `rv_freshness_pass`
  - `rv_staleness_reason`
- Enforced fail-closed behavior:
  - stale RV -> `data_quality_status=DATA_QUALITY_FAIL: stale_realized_vol`
  - stale RV -> `edge_attribution.explainable=false`, reason `stale_realized_vol`
  - stale RV -> `gates.allow_trade=false`
- Preserved missing RV behavior:
  - `DATA_QUALITY_FAIL: missing_realized_vol` unchanged.
- Added telemetry counter:
  - `telemetry.options_mc_runs_rv_stale_events`

## Tests
Executed:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_options_mc_realized_vol_feed_guard.py`
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`

Both passed.

## Commit
Implementation commit: `5b8145e`
