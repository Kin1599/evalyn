# Архитектура Sandbox

Этот документ описывает архитектурные решения и взаимодействие компонентов библиотеки Sandbox.

## Высокоуровневая архитектура

```
┌─────────────────────────────────────────────────────────┐
│                  Клиентский код (python)                │
├─────────────────────────────────────────────────────────┤
│                   SandboxManager API                    │
│  create_session() | get_session() | shutdown()          │
├─────────────────────────────────────────────────────────┤
│              SandboxSession (асинхронный)               │
│  execute_cell() | list_variables() | get_images() ...  │
├─────────────────────────────────────────────────────────┤
│                    Container (пул)                      │
│  create_kernel() | destroy_kernel() | send_command()   │
├─────────────────────────────────────────────────────────┤
│      GVisor runsc контейнер + KernelOrchestrator       │
│  (stdin/stdout JSON-RPC: execute, get_variables, ...)  │
├─────────────────────────────────────────────────────────┤
│           IPyKernel процессы + FS (overlayfs)          │
└─────────────────────────────────────────────────────────┘
```

## Компоненты

### 1. SandboxManager
Главная точка входа. Управляет жизненным циклом контейнеров и сессий.

**Ответственность:**
- Инициализация провайдеров (GVisorProvider, VenvStorage)
- Создание и переиспользование контейнеров
- Управление пулом контейнеров по venv_hash
- TTL сессий и контейнеров
- Фоновая очистка неактивных ресурсов

**Ключевые методы:**
```python
async def create_session(venv_name=None, requirements=None, ttl=None, files=None)
async def shutdown()
```

### 2. Container
Представляет один запущенный контейнер с одним оркестратором и пулом ядер.

**Ответственность:**
- Запуск/остановка процесса runsc
- Управление kernel_orchestrator через stdin/stdout
- Счётчик активных ядер
- Маршрутизация команд к оркестратору

**Ключевые методы:**
```python
async def create_kernel() -> str
async def destroy_kernel(kernel_id: str)
async def send_command(cmd: dict) -> dict
```

### 3. SandboxSession
Асинхронный интерфейс для взаимодействия клиента с одним ядром.

**Ответственность:**
- Управление ячейками ноутбука (парсинг, добавление)
- Выполнение кода и захват результатов
- Получение переменных и изображений
- Трансляция операций в команды к kernel_orchestrator

**Ключевые методы:**
```python
async def execute_cell(cell_id: str, timeout=None) -> CellResult
async def list_variables() -> List[VariableMeta]
async def get_images(cell_id: str) -> List[dict]
```

### 4. KernelOrchestrator
Скрипт, запускаемый внутри контейнера. Управляет пулом IPyKernel процессов.

**Ответственность:**
- Запуск/остановка IPyKernel процессов
- JSON-RPC сервер (stdin/stdout)
- Выполнение кода в ядрах и сбор результатов
- Управление состоянием (переменные, изображения)
- Работа с файловой системой

**Поддерживаемые команды:**
- `create_kernel` — новое ядро
- `destroy_kernel` — удалить ядро
- `execute` — выполнить код
- `get_variables` — список переменных
- `get_variable` — получить переменную
- `get_images` — получить изображения
- `read_file`, `write_file`, `list_files` — файлы
- `shutdown` — остановка всех ядер

### 5. GVisorProvider
Адаптер для запуска контейнеров через runsc.

**Ответственность:**
- Формирование команды runsc с overlay параметрами
- Запуск/остановка процесса контейнера
- Параметры ограничения ресурсов (CPU, память)
- Работа с stdin/stdout процесса

### 6. VenvStorage
Управление кэшированными виртуальными окружениями.

**Ответственность:**
- Кэширование окружений по хэшу требований или имени
- Сборка venv через `uv venv` и `uv pip install`
- Предотвращение дублирования при одновременных запросах
- Хранение read-only слоев для overlay

## Жизненный цикл операций

### Трафик создании сессии

```
client.create_session(venv_name="ds", ttl=600)
       ↓
manager._get_or_create_container(venv_hash)
       ↓
(новый контейнер?)
       ├─→ venv_storage.get_or_create() → /venvs/hash/
       ├─→ gvisor_provider.start(lower=/venvs/hash)
       │     → process, stdin, stdout
       ├─→ Container(container_id, venv_hash, process)
       └─→ containers[container_id] = container
       ↓
container.create_kernel()
       ↓
send {"cmd": "create_kernel"} to kernel_orchestrator
       ↓
kernel_orchestrator запускает ipykernel процесс
       ↓
return kernel_id
       ↓
SandboxSession(container, kernel_id)
       ↓
return session

client.execute_cell(cell_id, code, timeout=10)
       ↓
session.execute_cell(cell_id, timeout=10)
       ↓
container.send_command({
  "cmd": "execute",
  "kernel_id": kernel_id,
  "cell_id": cell_id,
  "code": "...",
  "timeout": 10
})
       ↓
kernel_orchestrator маршрутизирует команду
       ↓
ipykernel выполняет код
       ↓
kernel_orchestrator собирает stdout, stderr, images
       ↓
return {"status": "ok", "stdout": "...", "images": [...]}
       ↓
CellResult(stdout, stderr, images, ...)
```

## Файловая система в контейнере

**Структура:**

```
USER_HOME.sandbox_data/
├── venvs/                    # (нижний слой overlay, read-only)
│   ├── <venv_hash1>/
│   │   ├── bin/python
│   │   ├── lib/
│   │   └── ...
│   └── <venv_hash2>/
│       └── ...
├── containers/               # (рабочие директории)
│   ├── <container_id>/
│   │   ├── upper/           # (верхний слой overlay)
│   │   ├── work/            # (служебная директория overlay)
│   │   ├── workspace/       # (точка монтирования)
│   │   │   ├── notebook.ipynb
│   │   │   ├── data.csv
│   │   │   └── ...
│   │   └── kernels/         # (connection files ядер)
│   │       ├── kernel_1.json
│   │       ├── kernel_1/    # (unix socket)
│   │       └── ...
│   └── ...
```

**Overlay слои:**
- **Lower (read-only)** — venv из VenvStorage
- **Upper** — изменения в контейнере (package installs внутри workspace)
- **Merged (workspace)** — объединённый вид для ядра

## Параллелизм и синхронизация

### Правила

- **Внутри одного ядра** — код выполняется однопоточно (IPyKernel по умолчанию)
- **Между ядрами в контейнере** — полная параллельность (разные процессы)
- **Между сессиями в разных контейнерах** — полная параллельность
- **SandboxManager** — thread-safe (использует asyncio.Lock для критических секций)
- **Container** — thread-safe (очередь команд в каналы)

### TTL и очистка

**Сессия TTL:**
- Если `session.ttl` задан и истекает время неактивности → автоматический `terminate()`
- Проверка: фоновая задача менеджера каждые `container_cleanup_interval` сек

**Контейнер TTL:**
- Если `active_kernels == 0` и прошло `container_idle_ttl` сек → остановка контейнера
- Проверка: фоновая задача менеджера каждые `container_cleanup_interval` сек
- Позволяет переиспользовать контейнеры без пересоздания overlay

### Обрабатка ошибок

**Таймауты:**
- Если выполнение кода превышает `timeout` → interrupt ядра
- Если код не отзывается за 5 сек → kill яда (hard stop)
- Сессия может быть перезаведена или переиспользована с новым ядром

**Краши ядра:**
- Если ядро упало — сессия получит ошибку
- `restart_kernel()` создаст новое ядро в том же контейнере (состояние теряется)

**Потеря соединения с контейнером:**
- Если соединение разорвано → `ProtocolError`
- Менеджер останавливает контейнер
- Новые сессии создаются в новых контейнерах

## Безопасность

### Изоляция

- **gVisor** — микрокернель-подход к изоляции (защита от системных вызовов)
- **Отключённая сеть** — `--network=none` (только localhost)
- **Read-only venv** — предотвращение модификации окружения
- **Непривилегированный пользователь** — запуск ядер без прав root

### Ограничения ресурсов

- **CPU** — лимит через `runsc --cpu=<n>`
- **Память** — лимит через `runsc --memory=<mb>`
- **Ядра в контейнере** — максимум `max_kernels` штук
- **Время выполнения** — таймауты на уровне каждого вызова

### Сериализация

- **Pickle** — используется для сериализации переменных
  - ⚠️ Security: pickle может выполнять произвольный код, но контейнер изолирован
  - Добавить валидацию на уровне клиента в будущем (если требуется)

## Расширяемость

### Будущие варианты

1. **Множественные провайдеры изоляции**
   - `gvisor` (текущий)
   - `virtualbox` (более тяжелый)
   - `docker` (с ограничениями)

2. **Белый список модулей Python**
   - Запретить импорт опасных модулей (os.system, subprocess, etc.)

3. **Профилировка и мониторинг**
   - Логирование операций
   - Метрики (время выполнения, использованная память)

4. **Снимки состояния (snapshots)**
   - `export_state()` / `import_state()` для сессий
   - Повторное воспроизведение сценариев

5. **Коллаборативные сессии**
   - Один контейнер, несколько клиентов
   - Синхронизация состояния

## Примеры использования

### Базовый сценарий

```python
manager = SandboxManager(isolation="gvisor")
session = await manager.create_session(venv_name="default")
result = await session.execute_code("x = 42", timeout=5)
vars_ = await session.list_variables()
await session.terminate()
```

### Выполнение ноутбука

```python
session = await manager.create_session(venv_name="datascience")
await session.upload_file("notebook.ipynb", content)
cells = await session.open_notebook("notebook.ipynb")
for cell in cells:
    if cell.cell_type == "code":
        result = await session.execute_cell(cell.cell_id)
        if result.images:
            imgs = await session.get_images(cell.cell_id)
```

### Интерактивная сессия

```python
session = await manager.create_session(ttl=600)

# Добавиться ячейке
id1 = await session.add_cell("import numpy as np")
await session.execute_cell(id1)

# Добавить вторую
id2 = await session.add_cell("arr = np.array([1, 2, 3])")
await session.execute_cell(id2)

# Получить переменные
vars_ = await session.list_variables()
# [VariableMeta(name='np', type_name='module', size_bytes=...),
#  VariableMeta(name='arr', type_name='ndarray', size_bytes=...)]

# Экспортировать состояние
state = await session.export_state()
```
