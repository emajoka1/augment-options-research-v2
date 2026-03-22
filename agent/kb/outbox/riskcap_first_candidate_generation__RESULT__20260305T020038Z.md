- Ticket id: `riskcap_first_candidate_generation`

## Ticket summary
Immediate mission requested fixing the two active failures in `tests/test_mc_command.py` and ensuring full suite green while preserving risk-cap-first behavior and output contracts.

## What changed
- `scripts/mc_command.py`
  - Restored action-state contract used by tests and Telegram workflow:
    - `PARTIAL_DATA` or missing required fields -> `NO_TRADE`
    - `Final Decision=TRADE` with clean data -> `TRADE_READY`
    - otherwise -> `WATCH`
  - Kept `trade_ready_rule` diagnostics and gate reporting intact (no threshold relax).
- `scripts/spy_free_brief.py`
  - Enforced risk-cap-first candidate selection pre-ranking (no infeasible fallback pools).
- `tests/test_spy_free_brief_riskcap.py`
  - Added contract tests for strict cap behavior and exact NO_CANDIDATES message.

## Files changed
- `scripts/mc_command.py`
- `scripts/spy_free_brief.py`
- `tests/test_spy_free_brief_riskcap.py`

## Commands run + proof
1) Targeted failing area:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q tests/test_mc_command.py`
- Output:
  - `... [100%]`

2) Full suite:
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`
- Output:
  - `.......................... [100%]`

## Risks / follow-ups
- No schema key removals performed.
- No trading gate threshold relaxations performed.
- Follow-up ticket `bot_response_timeout_guard` (P0) remains pending in `kb/inbox`.

## Commit hash
- `69c1eb7` (mc_command contract fix)
- `42ae785` (risk-cap-first candidate generation)
