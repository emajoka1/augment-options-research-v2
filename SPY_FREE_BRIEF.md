# SPY Free/Public Brief (Fallback Mode)

This gives a **best-effort SPY options morning brief** using free/public sources and local chain data.

## What it fixes

- Replaces hard-fail style with `PARTIAL_DATA` when only chain structure exists.
- Produces a usable brief even without paid options feeds.
- Clearly marks what is missing before anything is trade-ready.

## Run

```bash
python3 scripts/spy_free_brief.py
```

## Unified MC command (recommended)

```bash
python3 scripts/mc_command.py --max-attempts 2 --retry-delay-sec 180
```

This wrapper:
- runs the live snapshot collector + brief generator,
- retries automatically when feed is `PARTIAL_DATA`,
- classifies state as `NO_TRADE` / `WATCH` / `TRADE_READY`,
- logs each run to `snapshots/mc_runs.jsonl`.

## State-change alerting (for cron)

Only emits when state changes (`action_state`, `data_status`, or `final_decision`):

```bash
python3 scripts/mc_notify_if_changed.py --max-attempts 2 --retry-delay-sec 180
```

Emit an OpenClaw wake event on changes:

```bash
python3 scripts/mc_notify_if_changed.py --notify
```

## Quick scorecard

```bash
python3 scripts/mc_scorecard.py
```

Shows run counts by action/data/decision and the last run snapshot.

Optional env vars:

- `SPY_CHAIN_PATH` (default: `~/lab/data/tastytrade/SPY_nested_chain.json`)
- `SPY_DXLINK_PATH` (default: `~/lab/data/tastytrade/dxlink_snapshot.json`)

## Output includes

- 5 catalyst links (public sources)
- Best-effort regime read (SPY, VIX, US10Y proxy, DXY proxy via Yahoo)
- Free options fallback via Cboe delayed quotes JSON (no API key)
- Top structural watchlist contracts (nearest expiries/near-ATM strikes)
- 3 defined-risk setup templates
- Explicit `missing_for_trade_ready` fields

## Limits (important)

Free/public mode does **not** guarantee live options microstructure fields:

- option bid/ask/mark/last per contract
- greeks + implied volatility per contract
- open interest and day volume per contract

So treat output as **research/planning**, not direct execution, until those fields are verified in broker platform.
