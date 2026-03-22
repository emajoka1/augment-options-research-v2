# API Gateway

Current status:
- proxies `/api/v1/*` to the FastAPI research engine
- health endpoint checks upstream FastAPI
- auth middleware scaffold with demo bearer tokens (`free-demo`, `pro-demo`)
- in-memory per-minute rate limiting (`100/min` free, `1000/min` pro)
- Clerk webhook stub endpoint at `/api/webhooks/clerk`

Env knobs:
- `FASTAPI_BASE_URL`
- `CORS_ORIGINS`
- `AUTH_OPTIONAL`
- `RATE_LIMIT_FREE_PER_MIN`
- `RATE_LIMIT_PRO_PER_MIN`
