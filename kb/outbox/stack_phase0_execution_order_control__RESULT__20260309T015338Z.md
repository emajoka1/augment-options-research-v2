# RESULT — stack_phase0_execution_order_control

## Summary
Implemented explicit execution-order control for stack phases (phase1 -> phase2 -> phase3) with fail-closed gating logic.

## Files changed
- `src/ak_system/ticket_phase_guard.py`
- `scripts/stack_phase_gate.py`
- `tests/test_ticket_phase_guard.py`

## What was implemented
- Canonical phase order constant for stack tickets.
- Gate function `phase_gate_status(ticket_id, outbox_dir)` that:
  - allows phase1 immediately,
  - blocks phase2 until phase1 `__RESULT__` proof exists,
  - blocks phase3 until phase2 `__RESULT__` proof exists,
  - permits non-stack tickets unchanged.
- CLI helper to enforce gate in automation:
  - `PYTHONPATH=src ./.venv/bin/python scripts/stack_phase_gate.py <ticket_id>`
  - exits non-zero when blocked.
- Unit tests covering allowed/blocked transitions.

## Test proof
Command:
`PYTHONPATH=src ./.venv/bin/python -m pytest -q`

Result:
`47 passed`

## Commit
`ba6f8b6`
