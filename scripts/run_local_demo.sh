#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
API_BASE=${RESEARCH_API_BASE:-http://127.0.0.1:8000}
API_HOST=${RESEARCH_API_HOST:-127.0.0.1}
API_PORT=${RESEARCH_API_PORT:-8000}
STREAMLIT_PORT=${STREAMLIT_PORT:-8501}

cleanup() {
  if [ -n "${API_PID:-}" ] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
  fi
  if [ -n "${ST_PID:-}" ] && kill -0 "$ST_PID" 2>/dev/null; then
    kill "$ST_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cd "$ROOT/services/research-engine"
PYTHONPATH=src ./.venv/bin/python -m uvicorn src.api.main:app --host "$API_HOST" --port "$API_PORT" &
API_PID=$!

cd "$ROOT/apps/streamlit"
python3 -m venv .venv >/dev/null 2>&1 || true
. .venv/bin/activate
pip install -r requirements.txt >/dev/null
RESEARCH_API_BASE="$API_BASE" streamlit run app.py --server.port "$STREAMLIT_PORT"
