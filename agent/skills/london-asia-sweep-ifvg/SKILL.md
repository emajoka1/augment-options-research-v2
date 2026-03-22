---
name: london-asia-sweep-ifvg
description: Intraday liquidity-sweep reversal playbook using Asia/London session highs and lows plus 1-3 minute iFVG confirmation, with strict risk and execution rules. Use when the user asks for session sweep setups, ICT-style liquidity grabs, iFVG entries, 1:2R plans, or wants concrete trade criteria for London/NY intraday index/FX trading.
---

# London/Asia Sweep + iFVG Playbook

Use this skill to turn a discretionary idea into a strict execution checklist.

## Workflow

1. Mark key liquidity
   - Asia high/low
   - London high/low
   - Current session open and VWAP (optional but recommended)

2. Wait for a sweep
   - Price takes one of those highs/lows (stop run)
   - Prefer a clear wick-through + close back inside prior range

3. Require reversal evidence on 1-3m
   - Strong displacement candle away from the sweep
   - iFVG appears in the opposite direction of the sweep

4. Define the trade
   - Entry: retrace into the iFVG
   - Stop: beyond sweep extreme
   - TP1: 1R
   - TP2: 2R or opposing liquidity pool

5. Enforce filters
   - Skip during low-liquidity chop
   - Skip 10-15 min before major high-impact news
   - Skip if no displacement after sweep

## Execution Rules (Survival-First)

- Risk per trade: 0.25%-0.75% max
- Do not widen stops after entry
- If spread/liquidity worsens materially, skip
- One clean setup is better than multiple low-quality attempts

## Setup Quality Score (quick)

Treat as A-grade only when all are true:
- Clean session-level sweep
- Fast displacement
- iFVG retrace entry available
- Clear 1:2R path before nearest opposing liquidity

If any is missing, downgrade or pass.

## Output Format for Live Calls

When asked for a live setup, respond with:
- Bias: long/short/none
- Swept level: Asia/London high/low
- iFVG zone: entry range
- Stop level
- TP1 (1R), TP2 (2R)
- Invalidation condition
- Position size guidance from risk %

## References

- Use `references/checklist.md` as the compact pre-trade checklist.
- Use `references/session-template.md` to log each setup for review and edge validation.
