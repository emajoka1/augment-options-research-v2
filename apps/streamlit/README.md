# Streamlit App

Minimal Streamlit frontend for `services/research-engine`.

## What it can do

- health check
- load chain
- load brief
- load vol surface
- analyze a custom strategy via JSON legs

## Run

From the repo root or this directory:

```bash
cd apps/streamlit
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export RESEARCH_API_BASE=http://localhost:8000
streamlit run app.py
# or, if your launcher expects the conventional filename:
streamlit run streamlit_app.py
```

If you want to use a gateway/proxy instead of the raw FastAPI app, point `RESEARCH_API_BASE` at that base URL.

## Notes

- The app is intentionally thin: it exercises the existing research-engine endpoints instead of reimplementing backend logic in Streamlit.
- It now uses a small cached HTTP client and short-TTL caching for GET requests (`health`, `chain`, `vol surface`).
- UI inputs/results persist in `st.session_state`, so reruns do not wipe the current symbol, JSON legs, or last responses.
- For `/v1/chain/{symbol}` and `/v1/vol-surface/{symbol}`, pass a `snapshot_path` if demo fallback is disabled and no live provider is configured.

## Streamlit Community Cloud / deploy plan

Recommended setup:

1. Deploy the research-engine backend somewhere public.
2. Deploy the Streamlit app separately.
3. Set Streamlit main file path to `streamlit_app.py`.
4. Set `RESEARCH_API_BASE=https://<your-public-backend>` in Streamlit secrets/env.

Architecture:

```text
Streamlit UI
   -> research-engine API
   -> provider/snapshot/dxLink-backed data
```

Do not point Streamlit directly at dxLink. dxLink is a market-data source for backend-side scripts/services, not the frontend integration layer.
