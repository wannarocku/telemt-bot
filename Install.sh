#!/bin/bash
set -e

# Параметры
APP_DIR=/opt/telemt-bot
SERVICE_USER=telemt
TELEMT_CONFIG="/etc/telemt/telemt.toml"

echo "=== Установка Telemt и TeleMT-bot ==="

# Установка зависимостей
apt update
apt install -y wget tar python3 python3-venv python3-pip nano git

# Создание системного пользователя telemt
if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Создаём системного пользователя $SERVICE_USER..."
    useradd -d /opt/telemt -m -r -U $SERVICE_USER
fi

# Установка Telemt
echo "Скачиваем и устанавливаем Telemt..."
wget -qO- "https://github.com/telemt/telemt/releases/latest/download/telemt-$(uname -m)-linux-$(ldd --version 2>&1 | grep -iq musl && echo musl || echo gnu).tar.gz" | tar -xz
mv telemt /bin/
chmod +x /bin/telemt

# Настройка конфигурации Telemt
mkdir -p /etc/telemt
chown -R $SERVICE_USER:$SERVICE_USER /etc/telemt

if [ ! -f "$TELEMT_CONFIG" ]; then
    echo "Создайте / отредактируйте конфиг Telemt: $TELEMT_CONFIG"
    nano $TELEMT_CONFIG
fi

# systemd для Telemt
if [ ! -f /etc/systemd/system/telemt.service ]; then
    cat <<EOF >/etc/systemd/system/telemt.service
[Unit]
Description=Telemt
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=/opt/telemt
ExecStart=/bin/telemt $TELEMT_CONFIG
Restart=on-failure
LimitNOFILE=65536
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
fi

systemctl daemon-reload
systemctl enable telemt
systemctl start telemt
systemctl status telemt

# Развёртывание бота
echo "=== Установка TeleMT-bot ==="
mkdir -p $APP_DIR
git clone . $APP_DIR || echo "Файлы уже скопированы"
chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR
cd $APP_DIR

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Отредактируйте $APP_DIR/.env и заполните токены"
fi

# systemd для бота
if [ ! -f /etc/systemd/system/telemt-bot.service ]; then
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
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/telemt_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
fi

systemctl daemon-reload
systemctl enable telemt-bot
systemctl start telemt-bot
systemctl status telemt-bot

echo "=== Установка завершена ==="
echo "Отредактируйте файлы конфигурации при необходимости"
