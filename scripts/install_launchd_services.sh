#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEST="$HOME/Library/LaunchAgents"
mkdir -p "$DEST" "$ROOT/.run/logs"
for name in com.emajoka.augment.dxlink com.emajoka.augment.api com.emajoka.augment.streamlit; do
  cp "$ROOT/scripts/$name.plist" "$DEST/$name.plist"
  if ! launchctl print "gui/$(id -u)/$name" >/dev/null 2>&1; then
    launchctl bootstrap "gui/$(id -u)" "$DEST/$name.plist"
    launchctl enable "gui/$(id -u)/$name" || true
  fi
  launchctl kickstart "gui/$(id -u)/$name" >/dev/null 2>&1 || true
done
i=0
while [ "$i" -lt 30 ]; do
  if curl -fsS http://127.0.0.1:8000/v1/live-status >/dev/null 2>&1 && curl -fsS http://127.0.0.1:8501 >/dev/null 2>&1; then
    echo "installed"
    exit 0
  fi
  i=$((i+1))
  sleep 1
done
echo "services started but health checks timed out" >&2
exit 1
