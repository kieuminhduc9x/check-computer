#!/bin/bash
# install.sh - Cai dat PC Monitor Pro tren macOS bang launchd (LaunchAgents).
#
# Cach dung:
#   cd scripts/macos
#   chmod +x install.sh
#   ./install.sh
#
# Go bo:
#   ./uninstall.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "Thu muc project: $PROJECT_DIR"

if [ ! -f "$ENV_FILE" ]; then
    echo "LOI: Khong tim thay file .env tai $ENV_FILE"
    echo "Hay copy .env.example thanh .env va dien thong tin truoc."
    exit 1
fi

# --- Kiem tra da dien BOT_TOKEN / ALLOWED_CHAT_IDS chua ---
BOT_TOKEN_LINE=$(grep -E '^BOT_TOKEN=' "$ENV_FILE" | cut -d'=' -f2-)
CHAT_IDS_LINE=$(grep -E '^ALLOWED_CHAT_IDS=' "$ENV_FILE" | cut -d'=' -f2-)

if [ -z "$BOT_TOKEN_LINE" ] || [[ "$BOT_TOKEN_LINE" == DAN_* ]] || \
   [ -z "$CHAT_IDS_LINE" ] || [[ "$CHAT_IDS_LINE" == DAN_* ]]; then
    echo "LOI: Ban chua dien BOT_TOKEN / ALLOWED_CHAT_IDS trong file .env"
    exit 1
fi

HEARTBEAT_MINUTES=$(grep -E '^HEARTBEAT_MINUTES=' "$ENV_FILE" | cut -d'=' -f2- || echo "60")
HEARTBEAT_MINUTES=${HEARTBEAT_MINUTES:-60}
HEARTBEAT_SECONDS=$((HEARTBEAT_MINUTES * 60))

PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "LOI: Khong tim thay python3. Cai bang: brew install python3"
    exit 1
fi
echo "Da tim thay Python tai: $PYTHON_BIN"

echo "Dang cai thu vien..."
"$PYTHON_BIN" -m pip install -r "$PROJECT_DIR/requirements.txt" --quiet

mkdir -p "$LAUNCH_AGENTS_DIR"

generate_plist() {
    local template="$1"
    local output="$2"
    sed -e "s#__PYTHON_BIN__#$PYTHON_BIN#g" \
        -e "s#__PROJECT_DIR__#$PROJECT_DIR#g" \
        -e "s#__HEARTBEAT_SECONDS__#$HEARTBEAT_SECONDS#g" \
        "$template" > "$output"
}

echo "Dang tao va nap cac LaunchAgent..."

for name in startup heartbeat listener; do
    TEMPLATE="$SCRIPT_DIR/com.pcmonitor.$name.plist.template"
    DEST="$LAUNCH_AGENTS_DIR/com.pcmonitor.$name.plist"
    generate_plist "$TEMPLATE" "$DEST"
    launchctl unload "$DEST" 2>/dev/null || true
    launchctl load -w "$DEST"
    echo "  OK: com.pcmonitor.$name"
done

echo ""
echo "================================================="
echo "HOAN TAT! Da cai 3 LaunchAgent (startup, heartbeat, listener)."
echo "Kiem tra: launchctl list | grep pcmonitor"
echo "Test ngay: $PYTHON_BIN $PROJECT_DIR/main.py test"
echo "Thu tren Telegram: gui /help cho bot cua ban"
echo "Log: $PROJECT_DIR/pc_monitor.log va pc_monitor_launchd.log"
