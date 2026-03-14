- Ticket id: `unify_riskcap_estimator_mc_brief`

## Ticket summary
Unified risk-cap/max-loss logic behind a shared estimator module and wired both brief generation and mc_command to consume consistent estimator outputs.

## Changes made
- Added shared estimator module:
  - `src/ak_system/risk/estimator.py`
  - canonical functions:
    - `risk_cap_dollars(...)`
    - `max_loss_debit(...)`
    - `max_loss_credit(...)`
    - `max_loss_condor(...)`
    - `estimate_structure_risk(...)`
- Added package exports:
  - `src/ak_system/risk/__init__.py`
- Refactored `scripts/spy_free_brief.py`:
  - uses shared estimator in candidate generation feasibility checks (debit/credit/condor)
  - uses shared estimator for max-loss calculation in `build_trade`
  - retains fail-closed behavior and existing gates
- Refactored `scripts/mc_command.py`:
  - computes and emits normalized estimator payload:
    - `risk_estimator.version`
    - `risk_estimator.max_loss`
    - `risk_estimator.risk_cap`
    - `risk_estimator.feasible_under_cap`
  - adds compatibility alias: `riskEstimator`
  - fail-closed integration: adds `risk_cap_exceeded_estimator` gate failure when applicable
  - added `src` path bootstrap so direct `python3 scripts/mc_command.py ...` works without manual PYTHONPATH
- Added regression tests:
  - `tests/test_unify_riskcap_estimator_mc_brief.py`
  - verifies representative structure max-loss parity (brief vs shared estimator)
  - verifies `mc_command` emits estimator keys and consistency

## Files changed
- `src/ak_system/risk/estimator.py`
- `src/ak_system/risk/__init__.py`
- `scripts/spy_free_brief.py`
- `scripts/mc_command.py`
- `tests/test_unify_riskcap_estimator_mc_brief.py`

## Commands run + proof
1) Affected tests:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_unify_riskcap_estimator_mc_brief.py`
- Output: `.. [100%]`

2) Full suite:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Output: `.................................... [100%]`

3) Manual command proof:
- `python3 scripts/mc_command.py --max-attempts 1 --retry-delay-sec 1 --json`
- Extracted:
  - `risk_estimator.version = v1`
  - `risk_estimator.max_loss = 0.0`
  - `risk_estimator.risk_cap = 250.0`
  - `risk_estimator.feasible_under_cap = True`
  - alias key present: `riskEstimator`

## Risks / follow-ups
- No risk/tail/stress thresholds relaxed.
- Telegram-facing existing keys preserved; estimator keys added with compatibility alias.
- Follow-up: optionally annotate candidate payload itself with estimator struct per candidate for richer diagnostics.

## Commit hash
- `e29d8fc`
