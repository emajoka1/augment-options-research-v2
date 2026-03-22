#!/usr/bin/env bash
set -euo pipefail
latest_framework="$(ls -t kb/experiments/framework-oos-*.json 2>/dev/null | head -n 1 || true)"
latest_mc="$(ls -t kb/experiments/options-mc-*.json 2>/dev/null | head -n 1 || true)"
echo "LATEST_FRAMEWORK=${latest_framework}"
echo "LATEST_OPTIONS_MC=${latest_mc}"
