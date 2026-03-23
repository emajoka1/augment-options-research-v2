# DXLink Candle Subscriber

Use `scripts/dxlink_candles.cjs` to request historical candle events over DXLink.

## Example
```bash
DXLINK_CANDLE_SYMBOL='SPY{=5m}' \
DXLINK_CANDLE_FROM_TIME=$(( $(date +%s) * 1000 - 24*60*60*1000 )) \
node scripts/dxlink_candles.cjs
```

## Defaults
- symbol: `SPY{=5m}`
- fromTime: now minus 24 hours (milliseconds)
- output: `~/lab/data/tastytrade/dxlink_candles.json`

## Requires
- valid live quote token at `~/lab/data/tastytrade/api_quote_token.json`
- or auto-refresh env:
  - `TT_CLIENT_ID`
  - `TT_CLIENT_SECRET`
  - `TT_REFRESH_TOKEN`

## Notes
- Uses DXLink `Candle` event type
- Uses COMPACT feed format
- `fromTime` is in milliseconds since epoch
- The final candle is the live/updating candle
