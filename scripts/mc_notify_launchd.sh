#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd /Users/forge/.openclaw/workspace
/usr/bin/python3 scripts/mc_notify_if_changed.py --skip-live --max-attempts 1 --retry-delay-sec 0 >> snapshots/mc_cron.log 2>&1
