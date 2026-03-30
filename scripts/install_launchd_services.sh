#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DEST="$HOME/Library/LaunchAgents"
mkdir -p "$DEST" "$ROOT/.run/logs"
for name in com.emajoka.augment.dxlink com.emajoka.augment.api com.emajoka.augment.streamlit; do
  cp "$ROOT/scripts/$name.plist" "$DEST/$name.plist"
  launchctl bootout "gui/$(id -u)" "$DEST/$name.plist" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$DEST/$name.plist"
  launchctl enable "gui/$(id -u)/$name" || true
  launchctl kickstart -k "gui/$(id -u)/$name"
done
echo "installed"
