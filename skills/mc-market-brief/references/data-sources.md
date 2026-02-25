# MC Data Sources

Use this file when user asks where MC data comes from.

## Primary Inputs

1. **dxFeed via DXLink** (token-authenticated client)
   - Used by `scripts/spy_live_snapshot.cjs`
   - Provides delayed/live options events where available: Quote, Greeks, Trade, Summary

2. **Local Tastytrade-derived chain/snapshot files**
   - Typical paths under `~/lab/data/tastytrade/`
   - Examples:
     - `SPY_nested_chain.json`
     - `spy_live_snapshot.json`
     - `dxlink_snapshot.json`

3. **Yahoo Finance chart API**
   - Endpoint family: `https://query1.finance.yahoo.com/v8/finance/chart/...`
   - Used for SPY/VIX/US10Y proxy series and regime calculations

4. **Public catalyst calendars (links)**
   - Investing economic calendar
   - ForexFactory calendar
   - Federal Reserve events/speakers
   - US Treasury auction/refunding calendar
   - MarketWatch earnings calendar

## Plain-English One-Liner

“MC is a hybrid brief: local DXLink/Tastytrade snapshots for options structure, Yahoo for macro proxies/regime, plus public event calendars for catalysts.”
