# telemt-proxy
Простой бот для телеграма, для управления telemt и просмотра метрик через API

Для функционирования бота из коробки в конфиге telemt должны быть указаны следующий параметры:

[server.api]
enabled = true
listen = "127.0.0.1:9091"
minimal_runtime_enabled = true    # ← включаем snapshot runtime
runtime_edge_enabled = true       # ← включаем детальные runtime метрики (топ соединений, пользователей)

[general.telemetry]
core_enabled = true
user_enabled = true
me_level = "normal"

а в .service unit-файле:
AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_NET_ADMIN
