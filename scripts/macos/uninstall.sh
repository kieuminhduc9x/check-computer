#!/bin/bash
# uninstall.sh - Go bo PC Monitor Pro tren macOS.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="$(command -v python3 || true)"

if [ -n "$PYTHON_BIN" ] && [ -f "$PROJECT_DIR/main.py" ]; then
    "$PYTHON_BIN" "$PROJECT_DIR/main.py" uninstall
    exit $?
fi

LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
for name in startup heartbeat listener; do
    PLIST="$LAUNCH_AGENTS_DIR/com.pcmonitor.$name.plist"
    if [ -f "$PLIST" ]; then
        launchctl unload "$PLIST" 2>/dev/null || true
        rm -f "$PLIST"
        echo "Da xoa: com.pcmonitor.$name"
    else
        echo "Khong ton tai (bo qua): com.pcmonitor.$name"
    fi
done
echo "Hoan tat go bo."
