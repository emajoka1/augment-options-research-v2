---
name: mc-market-brief
description: Generate and relay SPY market context (MC) briefs from local cron/snapshot pipelines, including data-quality state (OK/PARTIAL_DATA), regime, catalysts, watchlist contracts, and defined-risk structures. Use when user asks for MC updates, data source provenance, trade-readiness checks, or to run/refresh the SPY brief workflow.
---

# MC Market Brief

Run the local SPY MC pipeline, summarize clearly, and separate **planning** from **execution-ready** data.

## Workflow

1. Run live snapshot collector.
2. Run brief generator.
3. Parse output and classify as `TRADE` / `PASS` / `NO TRADE`.
4. Always call out missing required fields before any execution suggestion.
5. If asked “where is data from,” cite exact upstreams from `references/data-sources.md`.

## Commands

Use workspace-root paths.

```bash
node scripts/spy_live_snapshot.cjs
python3 scripts/spy_free_brief.py
```

If env overrides are needed, set:
- `SPY_CHAIN_PATH`
- `SPY_TOKEN_PATH`
- `SPY_LIVE_OUT` / `SPY_LIVE_PATH`
- `SPY_DXLINK_PATH`

## Output Contract

Include:
- Spot + timestamp (Europe/London)
- Regime/trend + VIX/rates direction
- Data status (`OK` or `PARTIAL_DATA`)
- Top watchlist symbols (or say unavailable)
- 3 defined-risk structures (directional + hedge + neutral)
- `missing_for_trade_ready` checklist

## Guardrails

- Treat `PARTIAL_DATA` as **research-only**.
- Never present a structure as executable without per-leg bid/ask/mark, OI, volume, and at least delta.
- Keep language decisive: if key fields are missing, outcome is `NO TRADE` or `PASS`.
