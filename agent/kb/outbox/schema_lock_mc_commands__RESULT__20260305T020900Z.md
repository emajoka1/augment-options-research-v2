- Ticket id: `schema_lock_mc_commands`

## Ticket summary
Locked `/mc prove_trade_ready` and `/mc why_no_candidates` contracts with explicit assertions, backward-compat alias checks, and contract documentation.

## Changes made
- Added contract documentation:
  - `docs/mc_command_contract.md`
- Added schema-lock tests:
  - `tests/test_mc_schema_contract.py`
  - Verifies required keys for `mc_command --json`:
    - `trace_ids`, `spot_integrity`, `mc_provenance`, `trade_ready_rule`, and mandatory subkeys
  - Verifies no-candidates reason path is preserved:
    - `raw["TRADE BRIEF"]["NoCandidatesReason"]`
  - Verifies `mc_why` includes stale-source marker and warning text
- Added backward-compat output aliases in `scripts/mc_command.py`:
  - `traceIds` -> `trace_ids`
  - `spotIntegrity` -> `spot_integrity`
  - `mcProvenance` -> `mc_provenance`
  - `tradeReadyRule` -> `trade_ready_rule`

## Files changed
- `scripts/mc_command.py`
- `tests/test_mc_schema_contract.py`
- `docs/mc_command_contract.md`

## Commands run + proof
1) Affected tests:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_mc_schema_contract.py`
- Output: `.... [100%]`

2) Full suite:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Output: `................................ [100%]`

3) Manual contract checks:
- `python3 scripts/mc_command.py --max-attempts 1 --retry-delay-sec 1 --json`
  - Proof extracted:
    - `has_keys True`
    - `trace_ids ['snapshot_id', 'brief_id', 'mc_id']`
    - `mc_provenance_keys_present True`
- `python3 scripts/mc_why.py`
  - Proof extracted:
    - line contains `source_stale=False` marker (stale-source marker present)

## Risks / follow-ups
- No trading-gate thresholds changed.
- No Telegram-facing key renames; added aliases for compatibility.
- Follow-up: optional stricter JSON-schema validator can be added if contracts expand further.

## Commit hash
- 
