#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
"$ROOT/scripts/install_launchd_services.sh" >/dev/null 2>&1 || true
open "http://localhost:8501"
