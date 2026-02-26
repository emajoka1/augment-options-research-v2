# MC Trigger Phrases

Treat these user inputs as the same action:

- `/mc`
- `/mc now`
- `run MC now`
- `run mc`
- `mc update`

Treat these as status commands:

- `/mc status`
- `mc status`
- `/mc scorecard`
- `mc scorecard`
- `/mc outcomes`
- `mc outcomes`

## Response Behavior

### For `/mc` style requests

1. Run:
   - `python3 scripts/mc_command.py --max-attempts 2 --retry-delay-sec 180`
2. Return concise summary with:
   - data status
   - action state (`NO_TRADE` / `WATCH` / `TRADE_READY`)
   - spot/regime
   - missing-for-trade-ready checklist
3. If action state is `NO_TRADE` due to `PARTIAL_DATA`, say you will retry on next cycle (or run manual retry if user asks).

### For `/mc status`

- Run `python3 scripts/mc_status.py` and return scheduler health + last MC state.

### For `/mc scorecard`

- Run `python3 scripts/mc_scorecard.py` and return aggregate run summary.

### For `/mc outcomes`

- Run `python3 scripts/mc_outcome_report.py` and return outcome performance summary.
