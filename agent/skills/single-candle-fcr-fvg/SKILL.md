---
name: single-candle-fcr-fvg
description: Opening-range intraday strategy using the first 5-minute candle range (FCR), 1-minute break/retest, and fair value gap (FVG) entry for 1:2R targeting. Use when the user asks about first-candle strategy, 9:30 open range breakouts/breakdowns, M1 FVG entries, or wants precise entries/stops/targets for NY open momentum setups.
---

# Single Candle FCR + FVG Strategy

Use this playbook for NY open momentum with strict risk control.

## Setup Definition

- FCR = first 5-minute candle range after open (typically 9:30-9:35 ET)
- Bias is taken from break + structure confirmation, not prediction
- Entry is executed on M1 using FVG retest

## Workflow

1. Mark FCR high and low after first 5-minute candle closes.
2. Wait for a clean break of FCR high (long) or FCR low (short).
3. Confirm displacement in break direction on M1.
4. Identify FVG formed during displacement.
5. Enter on retrace to FVG (do not chase extension).
6. Stop beyond invalidation swing / opposite edge of setup.
7. Take profit at 1R and 2R, or next liquidity pool.

## Long Rules

- Price breaks and closes above FCR high
- M1 bullish displacement prints
- Bullish FVG forms and is retested
- Entry at/inside FVG with stop below local invalidation

## Short Rules

- Price breaks and closes below FCR low
- M1 bearish displacement prints
- Bearish FVG forms and is retested
- Entry at/inside FVG with stop above local invalidation

## Risk Rules (Mandatory)

- Risk per trade: 0.25%-0.75% max
- Minimum RR at entry: 1:2
- No adding to losers
- No widening stop
- Skip if no displacement/FVG quality

## No-Trade Filters

- High-impact news within 10-15 minutes
- Very wide spread / poor liquidity
- Immediate reclaim back into FCR after break
- Choppy overlap with no clean impulse

## Output Format for Live Calls

When asked for a live setup, return:
- Direction (long/short/none)
- FCR high/low
- Break confirmation candle
- FVG entry zone
- Stop price
- TP1 (1R), TP2 (2R)
- Invalidation condition
- Position size based on risk %

## References

- `references/checklist.md` for pre-entry go/no-go
- `references/session-log-template.md` for review and edge tracking
