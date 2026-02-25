# MC Trigger Phrases

Treat these user inputs as the same action:

- `/mc`
- `/mc now`
- `run MC now`
- `run mc`
- `mc update`

## Response Behavior

1. Run:
   - `python3 scripts/mc_command.py --max-attempts 2 --retry-delay-sec 180`
2. Return concise summary with:
   - data status
   - action state (`NO_TRADE` / `WATCH` / `TRADE_READY`)
   - spot/regime
   - missing-for-trade-ready checklist
3. If action state is `NO_TRADE` due to `PARTIAL_DATA`, say you will retry on next cycle (or run manual retry if user asks).
