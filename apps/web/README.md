# Web App

Current status:
- chain viewer calls the local gateway when available
- inline Monte Carlo panel posts to the research engine through apps/api
- trade brief panel calls `/api/v1/brief/:symbol`
- strategy builder panel calls `/api/v1/strategy/analyze`
- vol surface panel calls `/api/v1/vol-surface/:symbol`
- when the local stack is unavailable, the UI now shows explicit placeholder/unavailable states instead of silently pretending requests succeeded
- frontend no longer depends on a fake `/tmp/demo-chain.json` snapshot path

Set:
- `NEXT_PUBLIC_API_BASE_URL=http://localhost:8787`
