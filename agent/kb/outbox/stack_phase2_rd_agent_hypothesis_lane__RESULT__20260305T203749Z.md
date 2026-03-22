- Ticket id: `stack_phase2_rd_agent_hypothesis_lane`

## Ticket summary
Implemented isolated RD-agent-style hypothesis lane that produces research artifacts only and cannot influence trade execution decisions.

## Dependency gate proof (phase order)
- Phase1 completion reference:
  - `kb/outbox/stack_phase1_akshare_qlib_adapter__RESULT__20260305T203503Z.md`
  - Includes full-suite pytest pass proof.
- Phase2 started only after Phase1 proof existed.

## Changes made
- Added research hypothesis lane module:
  - `src/ak_system/research/hypothesis_lane.py`
  - emits required fields:
    - assumptions
    - expected_edge_mechanism
    - invalidation
    - confidence_source
    - provenance (prompt_version, model_id, run_timestamp_utc, config_hash)
  - hard guard:
    - `can_set_trade_ready = False`
- Added phase2 runner:
  - `scripts/stack_phase2_hypothesis_run.py`
- Added tests:
  - `tests/test_stack_phase2_hypothesis_lane.py`
  - validates required fields + guardrail
  - validates hypothesis lane does not modify `mc_command` decision outputs

## Files changed
- `src/ak_system/research/hypothesis_lane.py`
- `scripts/stack_phase2_hypothesis_run.py`
- `tests/test_stack_phase2_hypothesis_lane.py`

## Commands run + proof
1) Affected tests:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_stack_phase2_hypothesis_lane.py`
- Output: `.. [100%]`

2) Full suite:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Output: `........................................ [100%]`

3) Manual phase artifact proof:
- `PYTHONPATH=src ./.venv/bin/python scripts/stack_phase2_hypothesis_run.py`
- Produced: `kb/experiments/hypothesis-20260305-203705.json`
- Evidence:
  - `lane=hypothesis`
  - `can_set_trade_ready=False`
  - provenance keys present: `config_hash`, `model_id`, `prompt_version`, `run_timestamp_utc`

4) Manual `mc_command --json` schema diff note (phase boundary):
- `python3 scripts/mc_command.py --max-attempts 1 --retry-delay-sec 1 --json`
- Required keys still present:
  - `trace_ids=True`
  - `spot_integrity=True`
  - `mc_provenance=True`
  - `trade_ready_rule=True`
- Breaking schema diff: **none**.

## Risks / follow-ups
- Hypothesis lane currently emits deterministic placeholder logic; model-plug-in remains future work.
- No execution gates or risk thresholds changed.

## Commit hash
- `17f2575`
