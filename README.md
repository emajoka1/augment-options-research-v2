# Augment Options Research v2

Monorepo status:
- `services/research-engine` → Python options research engine + FastAPI
- `apps/api` → Bun/Hono gateway
- `apps/web` → Next.js research UI
- `agent/` → OpenClaw operating files and agent-owned state

## Quick start

### Research engine
```bash
make -C services/research-engine install
make -C services/research-engine dev
```

### Gateway
```bash
cd apps/api
bun install
bun run dev
```

### Web
```bash
cd apps/web
pnpm install
pnpm dev
```

### Root helpers
```bash
pnpm dev
pnpm test
pnpm run dev:research
pnpm run test:research
```

## Current product surface
- chain viewer
- inline Monte Carlo execution
- trade brief panel
- strategy builder flow
- vol surface viewer
- async MC job endpoints
- gateway auth/rate-limit scaffolds
