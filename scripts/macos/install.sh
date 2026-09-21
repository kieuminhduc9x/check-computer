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

echo "Thu muc project: $PROJECT_DIR"

if [ ! -f "$ENV_FILE" ]; then
    echo "LOI: Khong tim thay file .env tai $ENV_FILE"
    echo "Hay copy .env.example thanh .env va dien thong tin truoc."
    exit 1
fi

BOT_TOKEN_LINE=$(grep -E '^BOT_TOKEN=' "$ENV_FILE" | cut -d'=' -f2-)
CHAT_IDS_LINE=$(grep -E '^ALLOWED_CHAT_IDS=' "$ENV_FILE" | cut -d'=' -f2-)

if [ -z "$BOT_TOKEN_LINE" ] || [[ "$BOT_TOKEN_LINE" == DAN_* ]] || \
   [ -z "$CHAT_IDS_LINE" ] || [[ "$CHAT_IDS_LINE" == DAN_* ]]; then
    echo "LOI: Ban chua dien BOT_TOKEN / ALLOWED_CHAT_IDS trong file .env"
    exit 1
fi

PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "LOI: Khong tim thay python3. Cai bang: brew install python3"
    exit 1
fi
echo "Da tim thay Python tai: $PYTHON_BIN"

echo "Dang cai thu vien..."
"$PYTHON_BIN" -m pip install -r "$PROJECT_DIR/requirements.txt" --quiet --break-system-packages 2>/dev/null || \
    "$PYTHON_BIN" -m pip install -r "$PROJECT_DIR/requirements.txt" --quiet

echo "Dang ky service khoi dong..."
"$PYTHON_BIN" "$PROJECT_DIR/main.py" install
