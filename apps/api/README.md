# API Gateway

Current status:
- proxies `/api/v1/*` to the FastAPI research engine
- health endpoint checks upstream FastAPI
- Clerk JWT verification when `CLERK_SECRET_KEY` is configured
- optional local-dev auth bypass via `AUTH_OPTIONAL=true`
- in-memory per-minute rate limiting (`100/min` free, `1000/min` pro)
- forwards resolved user subject/tier headers upstream
- Clerk webhook stub endpoint at `/api/webhooks/clerk`

Env knobs:
- `FASTAPI_BASE_URL`
- `CORS_ORIGINS`
- `CLERK_SECRET_KEY`
- `AUTH_OPTIONAL`
- `RATE_LIMIT_FREE_PER_MIN`
- `RATE_LIMIT_PRO_PER_MIN`
