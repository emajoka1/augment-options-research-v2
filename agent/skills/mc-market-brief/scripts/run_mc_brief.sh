#!/usr/bin/env bash
set -euo pipefail

# Run from workspace root.
cd "$(dirname "$0")/../../.."

echo "[mc] running live snapshot collector..."
node scripts/spy_live_snapshot.cjs

echo "[mc] generating brief..."
python3 scripts/spy_free_brief.py
