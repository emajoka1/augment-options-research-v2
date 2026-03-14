Ticket: options_mc_realized_vol_feed_guard
Branch: ticket/options_mc_realized_vol_feed_guard
Status: DONE

Summary
- Enforced a realized-vol contract in `scripts/ak_options_mc.py`:
  - Uses primary snapshot RV (`rv10`/`rv20`) when present.
  - Falls back to latest local `snapshots/spy_mc_snapshot_*.json` returns when primary RV is missing.
  - If RV remains unavailable, sets `data_quality_status=DATA_QUALITY_FAIL: missing_realized_vol`, forces `edge_attribution.explainable=false`, and fail-closes `gates.allow_trade=false`.
- Added RV provenance/freshness telemetry fields in payload:
  - `calibration.rv_source`, `calibration.rv_window_bars`, `calibration.rv_asof`, `calibration.rv_freshness_seconds`
  - `telemetry.options_mc_runs_total`, `telemetry.options_mc_rv_missing_events`
- Added regression tests in `tests/test_options_mc_realized_vol_feed_guard.py`:
  - verifies local fallback recovers RV contract
  - verifies missing RV fail-closed behavior and reason code

Proof
- Full test suite passed:
  - `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
  - Result: `54 passed`

Commit
- `ca23237`
