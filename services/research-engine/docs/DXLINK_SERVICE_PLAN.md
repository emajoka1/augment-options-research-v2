# DXLink Service Layer Plan

## Ranked by ROI for this tool

1. Automatic token refresh inside the streamer/snapshot path
2. Reconnect / retry strategy around websocket auth + feed setup
3. Separate historical candle subscriber
4. Long-running daemon mode
5. Dynamic subscription management
6. Multi-channel orchestration

## Why this order

The research tool benefits most from reliable inputs, not architectural elegance. Token freshness and reconnect safety matter more than advanced channel routing.

## Current implementation status

- [x] Live quote-token fetch script
- [x] Delayed/demo token rejection
- [ ] Streamer auto-refreshes token when missing/expired
- [ ] Reconnect/retry loop
- [ ] Candle subscriber script
- [ ] Daemon mode
- [ ] Dynamic subscriptions
- [ ] Multi-channel orchestration
