#!/bin/bash
# uninstall.sh - Go bo PC Monitor Pro tren Linux.

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
