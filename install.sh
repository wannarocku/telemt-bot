#!/bin/bash
set -e

APP_DIR=/opt/telemt-bot
SERVICE_USER=telemt

echo "=== Установка TeleMT-bot ==="

# Установка зависимостей
apt update
apt install -y python3 python3-venv python3-pip git nano

# Создание пользователя telemt, если ещё нет
if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Создаём системного пользователя $SERVICE_USER..."
    useradd -m -r -U -d $APP_DIR -s /usr/sbin/nologin $SERVICE_USER
fi

# Развёртывание бота
mkdir -p $APP_DIR
cp -r ./* $APP_DIR
chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR
cd $APP_DIR

# Виртуальное окружение
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Создание .env, если его нет
if [ ! -f .env ]; then
    cat <<EOF >.env
TELEGRAM_TOKEN=
ADMIN_ID=
OTHER_SETTING=
EOF
    echo "Создан файл $APP_DIR/.env. Пожалуйста, заполните переменные перед запуском бота."
fi

# Определяем Python-скрипт бота (берём первый *.py в папке)
BOT_FILE=$(ls $APP_DIR | grep '\.py$' | head -n1)
if [ -z "$BOT_FILE" ]; then
    echo "Ошибка: не найден Python-скрипт бота (*.py) в $APP_DIR"
    exit 1
fi
echo "Используем скрипт $BOT_FILE для запуска сервиса"

# systemd unit
cat <<EOF >/etc/systemd/system/telemt-bot.service
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
systemctl enable telemt-bot
systemctl restart telemt-bot
systemctl status telemt-bot

echo "=== Установка TeleMT-bot завершена ==="
