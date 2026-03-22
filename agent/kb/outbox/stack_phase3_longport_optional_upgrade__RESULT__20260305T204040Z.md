- Ticket id: `stack_phase3_longport_optional_upgrade`

## Ticket summary
Implemented optional Longport premium tier adapter + deterministic source arbitration policy (`OK_LIVE_PREMIUM -> OK_LIVE -> OK_FALLBACK`) with fail-closed unresolved arbitration behavior.

## Dependency gate proof (phase order)
- Phase2 completion reference:
  - `kb/outbox/stack_phase2_rd_agent_hypothesis_lane__RESULT__20260305T203749Z.md`
  - Includes full-suite pytest pass proof.
- Phase3 started only after Phase2 proof existed.

## Changes made
- Added optional Longport adapter:
  - `src/ak_system/adapters/longport_adapter.py`
  - strict credential check, explicit unavailable labeling, no hard dependency
- Added source arbitration module:
  - `src/ak_system/stack/source_arbitration.py`
  - deterministic precedence: `OK_LIVE_PREMIUM` -> `OK_LIVE` -> `OK_FALLBACK`
  - fail-closed on unresolved source or missing spot
- Added manual demo runner:
  - `scripts/stack_phase3_arbitration_demo.py`
- Added arbitration tests:
  - `tests/test_stack_phase3_longport_optional_upgrade.py`

## Files changed
- `src/ak_system/adapters/longport_adapter.py`
- `src/ak_system/stack/source_arbitration.py`
- `scripts/stack_phase3_arbitration_demo.py`
- `tests/test_stack_phase3_longport_optional_upgrade.py`

## Commands run + proof
1) Affected tests:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_stack_phase3_longport_optional_upgrade.py`
- Output: `... [100%]`

2) Full suite:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Output: `........................................... [100%]`

3) Manual proof (Longport disabled fallback):
- `unset LONGPORT_APP_KEY LONGPORT_APP_SECRET LONGPORT_ACCESS_TOKEN`
- `PYTHONPATH=src ./.venv/bin/python scripts/stack_phase3_arbitration_demo.py`
- Produced: `kb/experiments/stack-phase3-arbitration-demo.json`
- Evidence:
  - `longport_source=longport_unavailable`
  - `longport_tier=UNAVAILABLE`
  - arbitration selected `OK_LIVE` from `live` source

4) Manual `mc_command --json` schema diff note (phase boundary):
- `python3 scripts/mc_command.py --max-attempts 1 --retry-delay-sec 1 --json`
- Required keys still present:
  - `trace_ids=True`
  - `spot_integrity=True`
  - `mc_provenance=True`
  - `trade_ready_rule=True`
- Breaking schema diff: **none**.

## Risks / follow-ups
- Longport quote retrieval remains optional/placeholder until production credentials + SDK integration are enabled.
- No trade gate thresholds changed.

## Commit hash
- `9f964fa`
