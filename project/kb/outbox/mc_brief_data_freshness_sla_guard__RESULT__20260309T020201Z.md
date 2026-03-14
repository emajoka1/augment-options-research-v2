# RESULT: mc_brief_data_freshness_sla_guard

- Ticket: `mc_brief_data_freshness_sla_guard`
- Branch: `ticket/mc_brief_data_freshness_sla_guard`
- Commit: `5a43843ccfb4dddf0deeeab8394c9803bdd5bc05`

## What changed
- Added configurable freshness SLA via env/CLI (`MC_INPUT_MAX_AGE_SECONDS`, `--freshness-sla-seconds`).
- Added machine-readable freshness block on every normalized MC artifact:
  - `freshness.max_age_seconds`
  - `freshness.pass`
  - `freshness.inputs.options_mc_generated_at.{timestamp,age_seconds,max_age_seconds,fresh,reason}`
- Enforced fail-closed behavior when required input freshness fails:
  - `action_state=NO_TRADE`
  - trade rule failure reason code: `DATA_QUALITY_FAIL: stale_inputs`
- Added stale-data operator guidance to markdown rendering.

## Test evidence
- Command: `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_mc_command.py tests/test_mc_schema_contract.py`
- Result: `10 passed`
- Command: `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Result: `52 passed`

## Acceptance mapping
- Hard freshness SLA exposed as config: ✅
- Fail-closed on stale required input with explicit reason code: ✅
- Machine-readable freshness metadata on artifacts: ✅
- Operator-facing stale-data recovery guidance: ✅
- Unit/regression tests for fresh/stale/partial bypass: ✅
