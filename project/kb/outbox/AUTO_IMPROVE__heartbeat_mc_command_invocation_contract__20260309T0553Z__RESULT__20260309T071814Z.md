# RESULT: heartbeat_mc_command_invocation_contract

## Status
✅ Completed

## Ticket
- id: `heartbeat_mc_command_invocation_contract`
- source: `kb/inbox/AUTO_IMPROVE__heartbeat_mc_command_invocation_contract__20260309T0553Z.json`
- branch: `ticket/heartbeat_mc_command_invocation_contract`
- commit: `e2e31671a425e16fc7f2acc53446338e078f385d`

## What changed (minimal diff)
1. Added canonical heartbeat checker script:
   - `scripts/heartbeat_integrity_check.py`
   - Invokes MC via explicit command (`sys.executable scripts/mc_command.py --json`) instead of PATH-dependent `mc_command` alias.
   - Emits structured `HEARTBEAT_CHECK_FAILED` payload with reason `mc_command_unavailable` when canonical target is unavailable.
   - Tracks telemetry in `snapshots/heartbeat_metrics.json`:
     - `heartbeat_mc_command_unavailable_total`
     - `heartbeat_mc_command_unavailable_last_failure_ts`
   - Normalizes `command not found` into reason code (no raw shell leakage).

2. Updated heartbeat instructions:
   - `HEARTBEAT.md` now references canonical command:
     - `python3 scripts/mc_command.py --json`

3. Added contract tests:
   - `tests/test_heartbeat_mc_command_contract.py`
   - Covers:
     - PATH without `mc_command` still succeeds via canonical explicit command
     - missing canonical target returns `reason=mc_command_unavailable` and increments telemetry
     - integration-style field evaluation (`spot_integrity.ok`, `mc_provenance.source_stale`, `mc_provenance.counts_consistent`)
     - no raw `command not found` leakage in output

## Test evidence
- Targeted:
  - `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_heartbeat_mc_command_contract.py tests/test_mc_notify_if_changed.py`
  - Result: `6 passed`
- Full suite:
  - `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
  - Result: `67 passed`

## Notes
- Fail-closed behavior was preserved: failures still emit explicit structured failure states.
- `mc_command` JSON schema remains unchanged for downstream consumers.
