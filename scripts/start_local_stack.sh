#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
LOG_DIR=${LOG_DIR:-$ROOT/.run/logs}
PID_DIR=${PID_DIR:-$ROOT/.run/pids}
mkdir -p "$LOG_DIR" "$PID_DIR"

TASTY_ENV_FILE=${TASTY_ENV_FILE:-$HOME/.config/tastytrade.env}
[ -f "$TASTY_ENV_FILE" ] && . "$TASTY_ENV_FILE"

pkill -f 'dxlink_stream_daemon.cjs' 2>/dev/null || true
pkill -f 'uvicorn src.api.main:app' 2>/dev/null || true
pkill -f 'streamlit run app.py --server.port 8501' 2>/dev/null || pkill -f 'streamlit run app.py' 2>/dev/null || true
sleep 1

cd "$ROOT/services/research-engine"
nohup env DXLINK_US10Y_SYMBOL="${DXLINK_US10Y_SYMBOL:-/ZNU26:XCBT}" node scripts/dxlink_stream_daemon.cjs >"$LOG_DIR/dxlink.log" 2>&1 &
echo $! > "$PID_DIR/dxlink.pid"

nohup env PYTHONPATH=src ./.venv/bin/python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 >"$LOG_DIR/api.log" 2>&1 &
echo $! > "$PID_DIR/api.pid"

cd "$ROOT/apps/streamlit"
nohup sh -c '. .venv/bin/activate && RESEARCH_API_BASE=http://127.0.0.1:8000 streamlit run app.py --server.port 8501' >"$LOG_DIR/streamlit.log" 2>&1 &
echo $! > "$PID_DIR/streamlit.pid"

echo "started"
