#!/bin/bash
# install.sh - Cai dat PC Monitor Pro tren Linux bang systemd (--user).
#
# Cach dung:
#   cd scripts/linux
#   chmod +x install.sh
#   ./install.sh
#
# Go bo:
#   ./uninstall.sh
#
# LUU Y: dung systemd --user (chay theo tai khoan dang nhap, khong can root),
# phu hop de screenshot/lock hoat dong dung (can quyen truy cap man hinh cua
# user dang dang nhap). Neu muon service chay ca khi CHUA dang nhap (vi du
# tren server), chay them:
#   sudo loginctl enable-linger $USER

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

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

HEARTBEAT_MINUTES=$(grep -E '^HEARTBEAT_MINUTES=' "$ENV_FILE" | cut -d'=' -f2- || echo "60")
HEARTBEAT_MINUTES=${HEARTBEAT_MINUTES:-60}

PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "LOI: Khong tim thay python3. Cai bang: sudo apt install python3 python3-pip (Debian/Ubuntu)"
    exit 1
fi
echo "Da tim thay Python tai: $PYTHON_BIN"

echo "Dang cai thu vien..."
"$PYTHON_BIN" -m pip install -r "$PROJECT_DIR/requirements.txt" --quiet --break-system-packages 2>/dev/null || \
    "$PYTHON_BIN" -m pip install -r "$PROJECT_DIR/requirements.txt" --quiet

mkdir -p "$SYSTEMD_USER_DIR"

generate_unit() {
    local template="$1"
    local output="$2"
    sed -e "s#__PYTHON_BIN__#$PYTHON_BIN#g" \
        -e "s#__PROJECT_DIR__#$PROJECT_DIR#g" \
        -e "s#__HEARTBEAT_MINUTES__#$HEARTBEAT_MINUTES#g" \
        "$template" > "$output"
}

echo "Dang tao cac systemd unit..."
generate_unit "$SCRIPT_DIR/pcmonitor-startup.service.template"   "$SYSTEMD_USER_DIR/pcmonitor-startup.service"
generate_unit "$SCRIPT_DIR/pcmonitor-listener.service.template"  "$SYSTEMD_USER_DIR/pcmonitor-listener.service"
generate_unit "$SCRIPT_DIR/pcmonitor-heartbeat.service.template" "$SYSTEMD_USER_DIR/pcmonitor-heartbeat.service"
generate_unit "$SCRIPT_DIR/pcmonitor-heartbeat.timer.template"   "$SYSTEMD_USER_DIR/pcmonitor-heartbeat.timer"

systemctl --user daemon-reload

echo "Dang bat cac dich vu..."
systemctl --user enable --now pcmonitor-startup.service
systemctl --user enable --now pcmonitor-listener.service
systemctl --user enable --now pcmonitor-heartbeat.timer

echo ""
echo "================================================="
echo "HOAN TAT! Da cai va bat 3 dich vu (systemd --user)."
echo "Kiem tra: systemctl --user status pcmonitor-listener.service"
echo "Test ngay: $PYTHON_BIN $PROJECT_DIR/main.py test"
echo "Thu tren Telegram: gui /help cho bot cua ban"
echo "Log: $PROJECT_DIR/pc_monitor.log va pc_monitor_systemd.log"
echo ""
echo "Meo: neu muon dich vu chay ca khi ban CHUA dang nhap, chay:"
echo "  sudo loginctl enable-linger \$USER"
