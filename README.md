# telemt-proxy

Простой бот для Telegram, для управления telemt и просмотра метрик через API.

Для функционирования бота из коробки в конфиге `telemt.toml` должны быть указаны следующие параметры:

```toml
[server.api]
enabled = true
listen = "127.0.0.1:9091"
minimal_runtime_enabled = true    # ← включаем snapshot runtime
runtime_edge_enabled = true       # ← включаем детальные runtime метрики (топ соединений, пользователей)

[general.telemetry]
core_enabled = true
user_enabled = true
me_level = "normal"
```
А в .service unit-файле:
```ini
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_NET_ADMIN
```
