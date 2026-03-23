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

### Streamlit
```bash
cd apps/streamlit
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export RESEARCH_API_BASE=http://localhost:8000
streamlit run app.py
```

Or from the repo root, if your launcher expects the conventional filename there:

```bash
python3 -m venv apps/streamlit/.venv
source apps/streamlit/.venv/bin/activate
pip install -r apps/streamlit/requirements.txt
export RESEARCH_API_BASE=http://localhost:8000
streamlit run streamlit_app.py
```

### Root helpers
```bash
pnpm dev
pnpm test
pnpm run dev:research
pnpm run test:research
make run-streamlit
make demo-local
make web-install
make web-dev
make web-build
```

## Current product surface
- chain viewer
- inline Monte Carlo execution
- trade brief panel
- strategy builder flow
- vol surface viewer
- async MC job endpoints
- gateway auth/rate-limit scaffolds
