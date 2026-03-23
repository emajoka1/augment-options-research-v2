# Tastytrade DXLink Live Quote Setup

## Goal
Fetch a **live** `/api-quote-tokens` response and store it where the snapshot script expects it.

## Required env
- `TT_CLIENT_ID`
- `TT_CLIENT_SECRET`
- `TT_REFRESH_TOKEN`
- optional: `TT_BASE_URL` (defaults to `https://api.tastytrade.com`)
- optional: `TT_QUOTE_TOKEN_OUT`

## Fetch live quote token
```bash
cd services/research-engine
TT_CLIENT_ID=... \
TT_CLIENT_SECRET=... \
TT_REFRESH_TOKEN=... \
make tasty-quote-token
```

This writes by default to:
- `~/lab/data/tastytrade/api_quote_token.json`

## Safety checks
The fetch script refuses tokens when:
- `level != api`
- `dxlink-url` contains `demo`
- `dxlink-url` contains `delayed`

## Expected live token shape
```json
{
  "data": {
    "token": "...",
    "dxlink-url": "wss://tasty-openapi-ws.dxfeed.com/realtime",
    "level": "api"
  }
}
```

## Then run the snapshot script
Use your existing live snapshot flow after generating the token.
