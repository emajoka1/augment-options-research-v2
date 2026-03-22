# Web App

Current status:
- chain viewer calls the local gateway when available
- inline Monte Carlo panel posts to the research engine through apps/api
- trade brief panel calls `/api/v1/brief/:symbol`
- strategy builder panel calls `/api/v1/strategy/analyze`
- vol surface panel calls `/api/v1/vol-surface/:symbol`
- falls back to demo data/output when the local stack is not running

Set:
- `NEXT_PUBLIC_API_BASE_URL=http://localhost:8787`
