# telemt-bot for Telegram

Простой Telegram‑бот для управления [telemt](https://github.com/telemt/telemt) и просмотра метрик через его HTTP API.  
Позволяет:
- получать список пользователей, их статистику и ссылки;
- создавать и удалять пользователей;
- смотреть runtime‑метрики (Totals, Top by connections / throughput);
- генерировать QR‑коды для TLS‑ссылок.

---

## Требования:

- Установленный и настроенный `telemt` с включённым API.
- Linux‑хост с systemd.
- Python 3 (если бот устанавливается из исходников).
- Доступ к интернету для работы с Telegram API.

---

## Настройка telemt:

В `telemt.toml` должны быть включены API и runtime‑метрики:

```toml
[server.api]
enabled = true
listen = "127.0.0.1:9091"         # в примере API слушает localhost
minimal_runtime_enabled = true    # включаем snapshot runtime
runtime_edge_enabled = true       # включаем детальные runtime-метрики (топ соединений, пользователей)

[general.telemetry]
core_enabled = true
user_enabled = true
me_level = "normal"
```

В unit‑файле сервиса `telemt` должны быть права:

```ini
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_NET_ADMIN
```

---

## Переменные окружения (.env):

При установке скрипт `install.sh` создаёт файл `.env` рядом с ботом (`/opt/telemt-bot/.env`).  
После установки обязательно открой его и заполни нужными значениями:

```ini
BOT_TOKEN=
ADMIN_IDS=
TELEMT_BASE_URL=http://127.0.0.1:9091/v1
TELEMT_API_AUTH=
REQUEST_TIMEOUT=5
```

Где:

- `BOT_TOKEN` — токен бота от @BotFather.  
- `ADMIN_IDS` — список Telegram ID админов, через запятую.  
- `TELEMT_BASE_URL` — URL API telemt (в примере `http://127.0.0.1:9091/v1`).  
- `TELEMT_API_AUTH` — значение заголовка Authorization (если нужен), иначе можно оставить пустым.  
- `REQUEST_TIMEOUT` — таймаут HTTP‑запросов к API telemt в секундах (по умолчанию 5)
---

## Установка:

```bash
wget https://github.com/wannarocku/telemt-bot/archive/refs/heads/main.zip -O telemt-bot-main.zip
unzip telemt-bot-main.zip &&
cd telemt-bot-main &&
chmod +x install.sh
```
1. Запусти установку:
   ```bash
   sudo ./install.sh
   ```
2. Отредактируй `.env`.

3. Запусти сервис:
   ```bash
   sudo systemctl start telemt-bot
   ```

Проверка статуса:

```bash
sudo systemctl status telemt-bot
journalctl -u telemt-bot -f
```
---

## Удаление:

```bash
sudo systemctl stop telemt-bot
sudo systemctl disable telemt-bot
sudo rm -f /etc/systemd/system/telemt-bot.service
sudo systemctl daemon-reload
sudo rm -rf /opt/telemt-bot
```

---

## Основные возможности бота:

В Telegram (для администратора из `ADMIN_IDS`) доступны команды:

- `/start` — главное меню бота.
- `/users` — список пользователей telemt.
- `/user <username>` — краткая информация по конкретному пользователю.
- `/new <username>` — создать пользователя (с выводом Secret, TLS‑ссылки и QR‑кода).
- `/link <username>` — вывести TLS‑ссылки пользователя.
- `/del <username>` — удалить пользователя.
- `/stats` — показать runtime‑статистику (Totals, топ по соединениям и трафику).

Через inline‑меню:

- просмотр списка пользователей с пагинацией;
- просмотр информации по пользователю;
- получение ссылок;
- получение QR‑кода для TLS‑ссылки.

---

## Моменты:

- Бот работает только для Telegram‑ID из `ADMIN_IDS`, для остальных отвечает «Доступ запрещён».
- Все запросы к API telemt идут на `TELEMT_BASE_URL` с заголовком `Authorization: TELEMT_API_AUTH` (если он задан).
- Для корректной статистики нужны включённые `minimal_runtime_enabled` и `runtime_edge_enabled` в конфиге telemt.
- Скрипт установки создаёт пользователя telemt под которым будет работать служба `telemt-bot.service`
