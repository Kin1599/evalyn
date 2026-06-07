# Sandbox — Безопасное выполнение Jupyter-ноутбуков

Асинхронная Python-библиотека для безопасного выполнения Jupyter-ноутбуков и произвольного Python-кода в изолированных окружениях (gVisor) с интерактивным управлением ячейками, захватом состояния и изображений.

## Особенности

- **gVisor изоляция** — контейнеры на основе runsc
- **Переиспользование venv** — кэширование через overlayfs
- **Интерактивное выполнение** — произвольный порядок ячеек
- **Захват состояния** — переменные, stdout/stderr, изображения
- **Асинхронный API** — полная поддержка asyncio
- **Управление TTL** — автоматическая очистка ресурсов

## Документация

- [Архитектура](docs/architecture.md)
- [API Reference](docs/api.md)
- [Установка и настройка](docs/installation.md)

## Структура проекта

```
sandbox/
├── sandbox/                    # Основной пакет
│   ├── __init__.py
│   ├── manager.py              # SandboxManager
│   ├── container.py            # Container
│   ├── session.py              # SandboxSession
│   ├── gvisor_provider.py       # GVisorProvider
│   ├── venv_storage.py          # VenvStorage
│   ├── kernel_orchestrator.py   # Скрипт для контейнера
│   ├── models.py               # Dataclasses
│   ├── errors.py               # Исключения
│   └── utils.py                # Утилиты
├── tests/                      # Тесты
├── examples/                   # Примеры использования
├── docs/                       # Документация
├── requirements.txt
└── pyproject.toml
```

## План реализации

Проект разделен на **5 этапов**:

1. **Фундамент** — модели, ошибки, утилиты
2. **Провайдеры** — VenvStorage, GVisorProvider
3. **Ядро контейнера** — KernelOrchestrator
4. **Управление контейнерами** — Container, SandboxManager
5. **Интерфейсы** — SandboxSession, интеграционные тесты

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for detailed stages.
