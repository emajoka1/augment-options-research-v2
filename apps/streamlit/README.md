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

- The app is intentionally thin: it just exercises the existing research-engine endpoints.
- For `/v1/chain/{symbol}` and `/v1/vol-surface/{symbol}`, pass a `snapshot_path` if demo fallback is disabled and no live provider is configured.
