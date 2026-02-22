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

Optional env vars:

- `SPY_CHAIN_PATH` (default: `~/lab/data/tastytrade/SPY_nested_chain.json`)
- `SPY_DXLINK_PATH` (default: `~/lab/data/tastytrade/dxlink_snapshot.json`)

## Output includes

- 5 catalyst links (public sources)
- Best-effort regime read (SPY, VIX, US10Y proxy, DXY proxy via Yahoo)
- Top structural watchlist contracts (nearest expiries/near-ATM strikes)
- 3 defined-risk setup templates
- Explicit `missing_for_trade_ready` fields

## Limits (important)

Free/public mode does **not** guarantee live options microstructure fields:

- option bid/ask/mark/last per contract
- greeks + implied volatility per contract
- open interest and day volume per contract

So treat output as **research/planning**, not direct execution, until those fields are verified in broker platform.
