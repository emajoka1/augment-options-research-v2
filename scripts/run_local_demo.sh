#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
API_BASE=${RESEARCH_API_BASE:-http://127.0.0.1:8000}
API_HOST=${RESEARCH_API_HOST:-127.0.0.1}
API_PORT=${RESEARCH_API_PORT:-8000}
STREAMLIT_PORT=${STREAMLIT_PORT:-8501}
DXLINK_WAIT_SEC=${DXLINK_WAIT_SEC:-20}
STATUS_FILE=${DXLINK_STREAM_STATUS_OUT:-$HOME/lab/data/tastytrade/dxlink_live_status.json}
TOKEN_REFRESH_SCRIPT="$ROOT/services/research-engine/scripts/fetch_tasty_live_quote_token.py"
TOKEN_REFRESH_PY="$ROOT/services/research-engine/.venv/bin/python"
TASTY_ENV_FILE="${TASTY_ENV_FILE:-$HOME/.config/tastytrade.env}"
TASTY_ENV_FILE_FALLBACK="${TASTY_ENV_FILE_FALLBACK:-$HOME/.config/tastytrade/sandbox.env}"

cleanup() {
  if [ -n "${API_PID:-}" ] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
  fi
  if [ -n "${DX_PID:-}" ] && kill -0 "$DX_PID" 2>/dev/null; then
    kill "$DX_PID" 2>/dev/null || true
  fi
  if [ -n "${ST_PID:-}" ] && kill -0 "$ST_PID" 2>/dev/null; then
    kill "$ST_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# Load dedicated Tasty env first.
# Only fall back to sandbox when explicitly allowed, because this launcher expects live DXLink.
# Avoid sourcing interactive zsh config from /bin/sh because it may contain zsh-only commands.
ALLOW_SANDBOX_FALLBACK=${ALLOW_SANDBOX_FALLBACK:-0}
[ -f "$TASTY_ENV_FILE" ] && . "$TASTY_ENV_FILE" || true
if [ "$ALLOW_SANDBOX_FALLBACK" = "1" ] && [ -f "$TASTY_ENV_FILE_FALLBACK" ]; then
  . "$TASTY_ENV_FILE_FALLBACK"
fi

# Guardrails: refuse sandbox/cert config for the live demo launcher.
TT_BASE_URL_NORMALIZED=${TT_BASE_URL:-https://api.tastytrade.com}
case "$TT_BASE_URL_NORMALIZED" in
  *cert*|*sandbox*)
    echo "Refusing sandbox/cert TT_BASE_URL for live launcher: $TT_BASE_URL_NORMALIZED" >&2
    echo "Create $TASTY_ENV_FILE with live credentials, or set ALLOW_SANDBOX_FALLBACK=1 for explicit demo mode." >&2
    exit 1
    ;;
esac

if [ ! -f "$TASTY_ENV_FILE" ] && [ "$ALLOW_SANDBOX_FALLBACK" != "1" ]; then
  echo "Missing live Tastytrade env file: $TASTY_ENV_FILE" >&2
  echo "Create it with TT_BASE_URL/TT_CLIENT_ID/TT_CLIENT_SECRET/TT_REFRESH_TOKEN for live DXLink." >&2
  exit 1
fi

# Pre-refresh tasty quote token if credentials are available.
if [ -n "${TT_CLIENT_ID:-}" ] && [ -n "${TT_CLIENT_SECRET:-}" ] && [ -n "${TT_REFRESH_TOKEN:-}" ]; then
  "$TOKEN_REFRESH_PY" "$TOKEN_REFRESH_SCRIPT" >/dev/null 2>&1 || true
fi

cd "$ROOT/services/research-engine"
node scripts/dxlink_stream_daemon.cjs &
DX_PID=$!

# Wait until the daemon reports healthy status, not just file existence.
i=0
while [ "$i" -lt "$DXLINK_WAIT_SEC" ]; do
  if [ -f "$STATUS_FILE" ] && python3 - <<PY
import json
from pathlib import Path
p = Path(r'''$STATUS_FILE''')
try:
    data = json.loads(p.read_text())
    h = data.get('health') or {}
    raise SystemExit(0 if h.get('ok') and not h.get('stale') else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    break
  fi
  i=$((i+1))
  sleep 1
done

PYTHONPATH=src ./.venv/bin/python -m uvicorn src.api.main:app --host "$API_HOST" --port "$API_PORT" &
API_PID=$!

cd "$ROOT/apps/streamlit"
python3 -m venv .venv >/dev/null 2>&1 || true
. .venv/bin/activate
pip install -r requirements.txt >/dev/null
RESEARCH_API_BASE="$API_BASE" streamlit run app.py --server.port "$STREAMLIT_PORT"
