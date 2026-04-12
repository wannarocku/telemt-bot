#!/bin/bash
set -e

APP_DIR=/opt/telemt-bot
SERVICE_USER=telemt
SERVICE_NAME=telemt-bot
BOT_FILE=telemt-bot-qr.py

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

cp -a . "$APP_DIR/.."
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
cd "$APP_DIR"

python3 -m venv .venv
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r requirements.txt

if [ ! -f .env ]; then
    cat <<EOF > .env
BOT_TOKEN=
ADMIN_IDS=
TELEMT_API_BASE=http://127.0.0.1:9091/v1
TELEMT_API_AUTH=
EOF
    chown "$SERVICE_USER:$SERVICE_USER" .env
    chmod 600 .env
    echo "Создан файл $APP_DIR/.env. Заполни переменные перед запуском бота."
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
systemctl restart "$SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager

echo "=== Установка TeleMT-bot завершена ==="
