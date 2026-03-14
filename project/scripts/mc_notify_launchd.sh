#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd /Users/forge/.openclaw/workspace

# Optional secrets file for Telegram delivery:
# TG_BOT_TOKEN=123456:ABCDEF
# TG_CHAT_ID=7577147381
if [ -f "/Users/forge/.openclaw/workspace/.mc.env" ]; then
  source /Users/forge/.openclaw/workspace/.mc.env
fi

/usr/bin/python3 scripts/mc_notify_if_changed.py --max-attempts 1 --retry-delay-sec 0 --telegram --tg-chat-id 7577147381 >> snapshots/mc_cron.log 2>&1
/usr/bin/python3 scripts/mc_outcome_update.py >> snapshots/mc_cron.log 2>&1
