#!/bin/bash
# uninstall.sh - Go bo PC Monitor Pro tren Linux.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="$(command -v python3 || true)"

if [ -n "$PYTHON_BIN" ] && [ -f "$PROJECT_DIR/main.py" ]; then
    "$PYTHON_BIN" "$PROJECT_DIR/main.py" uninstall
    exit $?
fi

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
systemctl --user disable --now pcmonitor-startup.service 2>/dev/null || true
systemctl --user disable --now pcmonitor-listener.service 2>/dev/null || true
systemctl --user disable --now pcmonitor-heartbeat.timer 2>/dev/null || true
systemctl --user disable --now pcmonitor-heartbeat.service 2>/dev/null || true
rm -f "$SYSTEMD_USER_DIR/pcmonitor-startup.service"
rm -f "$SYSTEMD_USER_DIR/pcmonitor-listener.service"
rm -f "$SYSTEMD_USER_DIR/pcmonitor-heartbeat.service"
rm -f "$SYSTEMD_USER_DIR/pcmonitor-heartbeat.timer"
systemctl --user daemon-reload
echo "Hoan tat go bo."
