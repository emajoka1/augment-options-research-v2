- Ticket id: `options_mc_provenance_contract`

## Ticket summary
Implemented immutable provenance contract for options-MC artifacts, producer-side validation with fail-on-missing provenance, and consumer-side hard-fail in `mc_command` when provenance is missing/malformed.

## Changes made
- `scripts/ak_options_mc.py`
  - Added deterministic `config_hash` (SHA-256 over run-critical config).
  - Added mandatory top-level provenance keys to every artifact:
    - `generated_at`, `config_hash`, `n_batches`, `paths_per_batch`, `n_total_paths`, `base_seed`, `crn_scope`
  - Ensured `assumptions.n_paths` is populated and consistent.
  - Added `validate_provenance_payload(payload)` and fail artifact write on missing/invalid provenance.
- `scripts/mc_command.py`
  - Added `validate_mc_source_provenance(mc)`.
  - Extended `mc_provenance` with `config_hash`, `provenance_ok`, `provenance_errors`.
  - Added hard-fail guard in `main()`:
    - raises on invalid/missing provenance before decision output.
- Added tests:
  - `tests/test_options_mc_provenance_contract.py`
    - verifies generated artifact payload always includes required provenance and non-null `generated_at`.
    - verifies `mc_command` fails closed on missing provenance.

## Files changed
- `scripts/ak_options_mc.py`
- `scripts/mc_command.py`
- `tests/test_options_mc_provenance_contract.py`

## Commands run + proof
1) Affected tests:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_options_mc_provenance_contract.py`
- Output: `.. [100%]`

2) Full suite:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Output: `.................................. [100%]`

3) Manual provenance sample proof:
- `./.venv/bin/python scripts/ak_options_mc.py --n-batches 1 --paths-per-batch 100 --expiry-days 1 --dt-days 1`
- Sample artifact: `kb/experiments/options-mc-20260305-052252.json`
- Extracted fields:
  - `generated_at=2026-03-05T05:22:52.471421+00:00`
  - `config_hash_len=64`
  - `n_batches=1 paths_per_batch=100 n_total_paths=100 assumptions.n_paths=100`
  - `base_seed=42 crn_scope=same_model_same_structure_friction_only`

## Risks / follow-ups
- No threshold/gate relaxation done.
- JSON shape remains compatible; additional provenance validity metadata added in `mc_provenance`.

## Commit hash
- 
