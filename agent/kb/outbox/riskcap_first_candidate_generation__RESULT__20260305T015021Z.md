- Ticket id: `riskcap_first_candidate_generation`

## What was broken
1) Candidate generation could promote infeasible structures (over risk cap) by falling back to non-viable pools before ranking.
2) Full-suite contract was failing due a pre-existing normalize action-state regression in `scripts/mc_command.py` (tests expected `PARTIAL_DATA -> NO_TRADE` and clean TRADE -> `TRADE_READY`).

## What changed
### A) Ticket-required risk-cap-first implementation
- `scripts/spy_free_brief.py`
  - Added `risk_cap_dollars()` helper.
  - Debit candidate generation now selects only feasible legs (no fallback to infeasible pool).
  - Credit candidate generation now selects only feasible legs (no fallback to infeasible pool).
  - Condor generation now skips infeasible combinations entirely.
  - Hard-gate and risk framework reporting now use the same cap helper.

- `tests/test_spy_free_brief_riskcap.py` (new)
  - `test_riskcap_first_generation_enforces_cap_pre_selection`
  - `test_no_candidates_message_exact_and_diagnostics_present`

### B) Full-suite blocker fix (to satisfy shared contract)
- `scripts/mc_command.py`
  - Restored normalize action-state contract:
    - `PARTIAL_DATA` or missing required -> `NO_TRADE`
    - clean `Final Decision=TRADE` -> `TRADE_READY`
    - else `WATCH`
  - MC/steady diagnostics remain intact under `trade_ready_rule`; no Telegram schema changes.

## Files changed
- `scripts/spy_free_brief.py`
- `tests/test_spy_free_brief_riskcap.py`
- `scripts/mc_command.py`

## Commands run
- `./scripts/list_tickets.sh`
- `./.venv/bin/python -m pytest -q tests/test_spy_free_brief_riskcap.py`
- `PYTHONPATH=src ./.venv/bin/python -m pytest -q`

## Test output proof
- Focused acceptance tests: `2 passed`
- Full suite: `26 passed`

## Constraints check
- No gate relaxation to force trades.
- Fail-closed behavior preserved (`NO_CANDIDATES` exact string retained).
- Telegram-facing output schema unchanged.
- No secrets embedded.

## Commits
- `42ae785` — `fix(riskcap_first_candidate_generation): enforce risk-cap-first candidate selection`
- `69c1eb7` — `fix(riskcap_first_candidate_generation): preserve normalize action-state contract`

## Behavioural drift risk
- Low and intentional:
  - Candidate feasibility is now stricter/pre-ranking.
  - Action-state behavior now matches test contract and expected command semantics.
