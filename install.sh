#!/bin/bash
set -e

APP_DIR=/opt/telemt-bot
SERVICE_USER=telemt
SERVICE_NAME=telemt-bot
BOT_FILE=telemt-bot-qr.py

GREEN='\033[0;32m'
NC='\033[0m'

echo "=== Установка TeleMT-bot ==="

apt update
apt install -y python3 python3-venv python3-pip git nano

if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Создаём системного пользователя $SERVICE_USER..."
    useradd -m -r -U -d "$APP_DIR" -s /usr/sbin/nologin "$SERVICE_USER"
else
    echo "Пользователь $SERVICE_USER уже существует, продолжаем."
fi

mkdir -p "$APP_DIR"

cp -a ./. "$APP_DIR"/
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
cd "$APP_DIR"

python3 -m venv .venv
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
    cat <<EOF > "$APP_DIR/.env"
# Telegram BOT token you may get from @BotFather
BOT_TOKEN=

# BOT admin ID you may get from @Getmyid_bot
ADMIN_IDS=

# Telemt API should listen that IP (default is localhost)
TELEMT_API_BASE=http://127.0.0.1:9091/v1

# If you need secure 'talk' with telemt API
TELEMT_API_AUTH=

# How long will request wait for API to respond (default is 5)
REQUEST_TIMEOUT=5
EOF
    chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
fi

if [ ! -f "$APP_DIR/$BOT_FILE" ]; then
    echo "Ошибка: не найден Python-скрипт бота: $APP_DIR/$BOT_FILE"
    exit 1
fi

echo "Используем скрипт $BOT_FILE для запуска сервиса"

cat <<EOF >/etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=teleMT Telegram Bot
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/$BOT_FILE
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}TeleMT-bot успешно установлен.${NC}"
echo -e "${GREEN}Имя службы: $SERVICE_NAME${NC}"
echo -e "${GREEN}Файл конфигурации: $APP_DIR/.env${NC}"
echo -e "${GREEN}Сейчас откроется .env для заполнения.${NC}"
echo -e "${GREEN}После заполнения запусти службу командами:${NC}"
echo -e "${GREEN}systemctl restart $SERVICE_NAME${NC}"
echo -e "${GREEN}systemctl status $SERVICE_NAME --no-pager${NC}"
echo -e "${GREEN}========================================${NC}"

nano "$APP_DIR/.env"
