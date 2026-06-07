Отлично, теперь полная ясность. Собираем финальную архитектуру с учётом последних ответов:

- **Нет пула контейнеров** (не усложняем), контейнеры создаются по мере необходимости и переиспользуются, пока в них есть ядра.
- **Ограничение на количество ядер** в одном контейнере – вводим как параметр `max_kernels` (по умолчанию, скажем, 10).
- **Одна ВМ = много ядер**, без дополнительной изоляции между ними. Файловая система общая, состояние ядер независимо (у каждого свой глобальный неймспейс Python). Этого достаточно для наших сценариев, включая многопоточные задания (каждое ядро однопоточно, но при необходимости студент может использовать `threading` внутри своего кода – это допустимо, хотя и не изолировано между ядрами; нас это устраивает).

---

## Финальная архитектура библиотеки Sandbox

### Основные компоненты

```
SandboxManager
├── isolation_provider: GVisorProvider
├── venv_storage: VenvStorage
├── containers: Dict[str, Container]   # ключ – container_id
├── create_session(venv_name/requirements, ttl?, files?) → SandboxSession
├── shutdown_container(container_id)   (или автоматически при нуле ядер + TTL контейнера)
└── фоновая задача TTL для контейнеров (опционально)

Container
├── container_id: str
├── venv_hash: str
├── max_kernels: int
├── active_kernels: int
├── process: asyncio.subprocess.Process (gVisor runsc)
├── stdin, stdout (каналы связи с kernel_orchestrator)
├── send_command(cmd: dict) → await response
└── методы: create_kernel(), destroy_kernel(kernel_id), shutdown()

SandboxSession (асинхронный интерфейс для клиента)
├── session_id: str
├── container: Container
├── kernel_id: str
├── cells: Dict[str, CellInfo]   (локальный кэш структуры ноутбука)
├── file_registry: Dict[str, bytes] (локальное зеркало или ленивая загрузка; фактически все файлы хранятся в контейнере, здесь можно держать метаданные)
├── upload_file(name, content)
├── get_file(name) → bytes
├── list_files() → List[str]
├── open_notebook(filename) → List[CellInfo]
├── add_cell(code, origin="added") → cell_id
├── execute_cell(cell_id, timeout?) → CellResult
├── execute_code(code, timeout?) → CellResult
├── list_cells() → List[CellInfo]
├── get_cell(cell_id) → CellInfo
├── list_variables() → List[VariableMeta]
├── get_variable(name) → pickle bytes
├── get_images(cell_id?) → List[ImageData]
├── export_state() → bytes (pickle всего namespace ядра)
├── cancel_cell() → прерывание текущего выполнения
├── shutdown_kernel() → уничтожает ядро, контейнер может остаться
└── terminate() → уничтожает ядро и, если контейнер пуст, останавливает контейнер
```

### 1. Управление окружениями (VenvStorage)

- Хранилище по пути `USER_HOME.sandbox_data/venvs/`.
- Ключ – хэш от `requirements.txt` (или имя, если передано явно).
- При создании сессии:
  - Если передан `venv_name`, ищется готовое окружение.
  - Если передан `requirements`, вычисляется хэш, при отсутствии создаётся через `uv venv` и `uv pip install`.
- Для каждого окружения хранится read-only слой, который будет монтироваться в контейнеры через overlayfs (нижний слой).
- Верхний слой (workspace) создаётся при старте контейнера и уничтожается при его остановке.

### 2. Контейнер и GVisorProvider

- **GVisorProvider** оборачивает `runsc do` и предоставляет асинхронный интерфейс:
  - `start(overlay_lowerdir, workspace_path) → (process, stdin, stdout)`
  - Внутри контейнера сразу запускается `kernel_orchestrator.py`, который слушает stdin/stdout.
- **Container** инкапсулирует процесс и ведёт учёт ядер.
  - `create_kernel()` отправляет `{"cmd":"create_kernel"}` → получает `kernel_id`, увеличивает `active_kernels`.
  - `destroy_kernel(kernel_id)` отправляет `{"cmd":"destroy_kernel", "kernel_id":"..."}` → уменьшает счётчик.
  - При `active_kernels == 0` и истечении TTL контейнера (задаётся глобально) – контейнер останавливается.
  - `max_kernels` проверяется перед созданием нового ядра; если превышен, можно либо создать новый контейнер с тем же окружением, либо вернуть ошибку (решает менеджер).

### 3. Kernel Orchestrator (внутри контейнера)

Скрипт `kernel_orchestrator.py`, который:
- Импортирует `ipykernel.kernelapp.IPKernelApp` и управляет словарём `kernels: Dict[str, Kernel]`.
- `create_kernel`: запускает новое ядро (в отдельном процессе? или в том же процессе, но в отдельном глобальном пространстве?). Надёжнее запускать отдельный процесс для каждого ядра, чтобы обеспечить независимость крашей. Используем `multiprocessing` или `subprocess` с ipython kernel, подключённым через пайпы. Оркестратор будет пробрасывать команды в конкретный процесс.
  - Для простоты и стабильности можно каждое ядро запускать как отдельный процесс через `subprocess.Popen` с `python -m ipykernel_launcher -f connection_file.json`, а оркестратор подключается к ним через jupyter_client. Однако это требует сети (внутри контейнера можно использовать tcp на localhost или unix-сокеты). Поскольку мы внутри контейнера и сеть может быть ограничена, но localhost обычно разрешён. Использование unix-сокетов для каждого ядра было бы надёжнее. Jupyter kernel поддерживает транспорт через файлы (connection file с указанием сокетов). Оркестратор будет управлять этими connection file'ами и создавать клиенты `jupyter_client.BlockingKernelClient` (в отдельных потоках, с асинхронными обёртками). Это стандартный способ.
- Альтернатива – использовать `IPython.parallel` или просто держать все ядра в одном процессе с разными неймспейсами, но это чревато: исключение в одном ядре может затронуть другие. Поэтому отдельные процессы.
- Оркестратор принимает команды через stdin/stdout в формате JSON-RPC, добавляет `kernel_id` для маршрутизации.
- Команды:
  ```json
  {"cmd":"create_kernel"}
  {"cmd":"destroy_kernel","kernel_id":"..."}
  {"cmd":"execute","kernel_id":"...","cell_id":"...","code":"...","timeout":30}
  {"cmd":"get_variables","kernel_id":"..."}
  {"cmd":"get_variable","kernel_id":"...","name":"x"}
  {"cmd":"get_images","kernel_id":"...","cell_id":"..."}
  {"cmd":"list_files","path":"."}
  {"cmd":"read_file","path":"..."}
  {"cmd":"write_file","path":"...","content":"base64..."}
  {"cmd":"shutdown"}
  ```
- Управление изображениями: оркестратор хранит для каждого ядра словарь `images: Dict[cell_id, List[ImageData]]`, очищается при вызове `get_images` (или хранится до перезаписи при новом выполнении той же ячейки).

### 4. Песочница сессии (SandboxSession)

- При создании сессии через `manager.create_session(...)`:
  1. Находим или создаём контейнер с нужным окружением (по venv_hash). Если контейнер существует и `active_kernels < max_kernels`, используем его, иначе создаём новый.
  2. В контейнере вызываем `create_kernel()` → получаем `kernel_id`.
  3. Создаём `SandboxSession(container, kernel_id)`, присваиваем `session_id`.
  4. Если переданы файлы, загружаем их в контейнер через `write_file`.
- Все методы сессии асинхронны, делегируют команды оркестратору с указанием `kernel_id`.
- Управление ячейками реализовано на стороне библиотеки (в `session.cells`). При `open_notebook` файл `.ipynb` читается из контейнера (через `read_file`), парсится, создаются объекты `CellInfo` с id.
- При выполнении ячейки код отправляется с её `cell_id`. Результат содержит список id изображений, которые можно потом запросить.
- `terminate()` вызывает `destroy_kernel` в контейнере, а затем, если в контейнере не осталось ядер, опционально останавливает контейнер (с учётом TTL). `shutdown_kernel()` только уничтожает ядро.

### 5. TTL и очистка

- У сессии может быть TTL (неактивности) – отслеживается менеджером. При истечении сессия автоматически `terminate()`.
- Контейнер без ядер может жить ещё некоторое время (глобальный `container_idle_ttl`, например 300 секунд), чтобы переиспользоваться без пересоздания. Фоновая задача менеджера раз в 60 секунд проверяет неактивные контейнеры и останавливает их.

### 6. Безопасность и ограничения

- gVisor с профилем безопасности: отключена сеть (кроме localhost, если нужен для связывания ядер, но мы используем unix-сокеты, так что сеть можно полностью отключить).
- Ресурсы CPU и памяти ограничиваются через `runsc` (--cpu, --memory).
- Белый список модулей пока не реализуем.
- Ограничение на количество ядер в контейнере предотвращает чрезмерное потребление ресурсов.

### 7. Пример использования

```python
import asyncio
from sandbox import SandboxManager

async def main():
    manager = SandboxManager(
        isolation="gvisor",
        venv_storage="USER_HOME.sandbox_data/venvs"
    )

    # Создание первой сессии (автоматически поднимется контейнер с datascience-py311)
    session1 = await manager.create_session(
        venv_name="datascience-py311",
        ttl=600
    )
    await session1.upload_file("notebook.ipynb", open("nb.ipynb","rb").read())
    cells = await session1.open_notebook("notebook.ipynb")
    for cell in cells:
        if cell.cell_type == "code":
            result = await session1.execute_cell(cell.id, timeout=10)
            print(result.stdout)

    # Создание второй сессии в том же окружении – она использует тот же контейнер, если есть свободные слоты для ядер
    session2 = await manager.create_session(
        venv_name="datascience-py311",
        ttl=300
    )
    # session2 может работать с другими файлами, состояние полностью изолировано от session1
    await session2.execute_code("x = 42", timeout=5)
    vars_meta = await session2.list_variables()
    print(vars_meta)

    # Завершение
    await session1.terminate()
    await session2.terminate()
    # Контейнер остановится после истечения idle_ttl, если не осталось ядер

asyncio.run(main())
```

### 8. Дополнительные замечания

- **Многопоточность в задании:** каждое ядро – обычный Python-процесс, студент может использовать `threading` внутри своего кода. Никакой дополнительной изоляции между потоками не требуется.
- **Производительность:** запуск нового ядра внутри контейнера – лёгкая операция (доли секунды). Контейнер с gVisor стартует быстро (~1-2 секунды). Overlayfs позволяет мгновенно создать рабочую область.
- **Обработка ошибок:** если ядро упало, сессия может попытаться пересоздать ядро в том же контейнере (метод `restart_kernel()`) с потерей состояния, но сохранением файлов.

---

Архитектура полностью покрывает все требования, включая интерактивное управление ноутбуком, многоэтапность, захват состояния и изображений. Готов переходить к реализации: написание `kernel_orchestrator.py`, `GVisorProvider`, `SandboxManager` и `SandboxSession` с документацией.


## Техническое задание на библиотеку «Sandbox»

### 1. Общее описание

Библиотека `sandbox` предоставляет асинхронный Python API для безопасного выполнения Jupyter-ноутбуков и произвольного Python-кода в изолированных средах (gVisor) с возможностью интерактивного управления ячейками, захвата состояния переменных, stdout/stderr и графических объектов. Библиотека предназначена для использования как в составе веб-сервисов (через дальнейшую обёртку REST/gRPC), так и напрямую в Python-коде (например, в Check Engine).

Ключевые особенности:
- Изоляция на основе gVisor (runsc) – один контейнер может содержать несколько независимых ядер IPython.
- Переиспользование окружений через overlayfs (кэширование venv).
- Интерактивное выполнение ноутбуков: произвольный порядок ячеек, добавление новых, повторное выполнение.
- Захват и сериализация глобального состояния (переменные) через pickle.
- Захват изображений (matplotlib) с возможностью отложенной загрузки.
- Управление временем жизни (TTL) сессий и контейнеров.
- Асинхронный API (asyncio) с поддержкой таймаутов и отмены операций.

### 2. Архитектура компонентов

Библиотека состоит из следующих основных компонентов:

1. **SandboxManager** – главная точка входа, управляет жизненным циклом контейнеров и сессий.
2. **Container** – представляет изолированную среду (gVisor), внутри которой работает оркестратор ядер.
3. **SandboxSession** – интерфейс взаимодействия с конкретным ядром (одна сессия = одно ядро).
4. **KernelOrchestrator** – процесс внутри контейнера, управляющий несколькими независимыми IPython-ядрами.
5. **GVisorProvider** – адаптер для работы с runsc (запуск, остановка, сигналы).
6. **VenvStorage** – менеджер кэшированных виртуальных окружений.

Взаимодействие:
- `SandboxManager` использует `GVisorProvider` для запуска контейнеров и `VenvStorage` для получения готовых окружений.
- Каждый `Container` при старте запускает `kernel_orchestrator.py`, который слушает stdin/stdout.
- При создании сессии `SandboxSession` получает ссылку на `Container` и `kernel_id`.
- Все операции сессии транслируются в JSON-команды к `kernel_orchestrator` с указанием `kernel_id`.

### 3. Компонент: SandboxManager

#### Параметры конструктора
- `isolation: str` – "gvisor" (в будущем можно добавить "virtualbox").
- `venv_storage_path: str` – путь к хранилищу окружений.
- `container_idle_ttl: int = 300` – время жизни контейнера без ядер (секунды).
- `container_max_kernels: int = 10` – максимальное число ядер в одном контейнере.
- `container_cleanup_interval: int = 60` – интервал проверки неактивных контейнеров (секунды).

#### Асинхронные методы
- `async create_session(venv_name: str = None, requirements: List[str] = None, ttl: Optional[int] = None, files: Optional[Dict[str, bytes]] = None) -> SandboxSession`
  - Создаёт новую сессию. Определяет venv_hash (по имени или требованиям). Находит или создаёт подходящий контейнер (у которого `active_kernels < max_kernels` и совпадает venv_hash). Создаёт в нём новое ядро, оборачивает в `SandboxSession`. Загружает начальные файлы, если переданы.
  - `ttl` – таймаут неактивности сессии (сек). Если не указан, сессия живёт до явного завершения.

- `async get_session(session_id: str) -> Optional[SandboxSession]` – получить сессию по ID.

- `async shutdown_container(container_id: str)` – принудительно остановить контейнер.

- `async shutdown()` – завершить все сессии и контейнеры.

- Внутренние:
  - `_cleanup_loop()` – фоновая задача, периодически останавливает контейнеры с `active_kernels == 0` и истёкшим `idle_ttl`, а также сессии с истёкшим TTL неактивности.
  - `_get_or_create_container(venv_hash: str) -> Container` – создаёт контейнер или возвращает существующий с доступным слотом для ядра.

### 4. Компонент: Container

#### Свойства
- `container_id: str`
- `venv_hash: str`
- `process: asyncio.subprocess.Process` – процесс runsc.
- `stdin, stdout` – каналы связи с KernelOrchestrator.
- `active_kernels: int`
- `last_activity: float` – время последней операции с любым ядром.

#### Методы
- `async create_kernel() -> str` (возвращает `kernel_id`)
  - Отправляет команду `{"cmd":"create_kernel"}`, получает `{"kernel_id":"..."}`.
- `async destroy_kernel(kernel_id: str)`
  - Отправляет `{"cmd":"destroy_kernel","kernel_id":"..."}`.
- `async send_command(cmd: dict) -> dict`
  - Увеличивает `last_activity`. Отправляет JSON-строку в stdin, читает ответ из stdout (разделитель – `\n`).
- `async shutdown()`
  - Отправляет `{"cmd":"shutdown"}`, ожидает завершения процесса, очищает workspace.

### 5. Компонент: SandboxSession

#### Атрибуты
- `session_id: str` (уникальный UUID)
- `container: Container`
- `kernel_id: str`
- `cells: OrderedDict[str, CellInfo]` – локальное представление ячеек ноутбука.
- `_last_activity: float` – для TTL.

#### Методы (все асинхронные)

**Файловые операции:**
- `async upload_file(name: str, content: bytes)` – записывает файл в контейнер через `write_file`.
- `async get_file(name: str) -> bytes` – читает файл.
- `async list_files() -> List[str]` – список файлов в рабочей директории.

**Управление ноутбуком:**
- `async open_notebook(filename: str) -> List[CellInfo]`
  - Читает `.ipynb` файл, парсит JSON. Для каждой ячейки кода создаёт `CellInfo` с полями:
    - `cell_id: str` (UUID из метаданных или сгенерированный)
    - `cell_type: str` ("code" или "markdown")
    - `source: str`
    - `origin: str` = "original"
    - `metadata: dict`
  - Сохраняет в `self.cells`. Возвращает список.
  - Markdown-ячейки тоже сохраняются, но не выполняются.

- `async add_cell(code: str, origin: str = "added") -> str` (возвращает cell_id)
  - Создаёт новую ячейку с типом "code", генерирует UUID, добавляет в `self.cells`.

- `async list_cells() -> List[CellInfo]` – возвращает все ячейки.
- `async get_cell(cell_id: str) -> CellInfo` – возвращает конкретную ячейку.

**Выполнение кода:**
- `async execute_cell(cell_id: str, timeout: Optional[int] = None) -> CellResult`
  - Находит ячейку по `cell_id`, отправляет команду `execute` с кодом этой ячейки и `cell_id`.
  - `CellResult` содержит:
    - `stdout: str`
    - `stderr: str`
    - `images: List[dict]` – список `{"id": "img1", "format": "png"}` (только метаданные)
    - `error: Optional[dict]` – информация об ошибке, если есть
    - `cell_id: str`

- `async execute_code(code: str, timeout: Optional[int] = None) -> CellResult`
  - Выполняет произвольный код вне системы ячеек. `cell_id` не передаётся (или используется специальный, например "adhoc"). Изображения могут сохраняться под этим id.

**Переменные:**
- `async list_variables() -> List[dict]`
  - Возвращает список `[{"name":"x", "type":"int", "size":28}, ...]`.
- `async get_variable(name: str) -> bytes`
  - Возвращает pickle-сериализованное значение переменной (base64 декодируется в bytes).

**Изображения:**
- `async get_images(cell_id: Optional[str] = None) -> List[dict]`
  - Возвращает список изображений: `[{"id":"img1", "format":"png", "data": base64_bytes}, ...]`.
  - Если `cell_id` не указан, возвращаются изображения последней выполненной ячейки (или все накопленные? Уточним: по умолчанию – последняя ячейка, если нужно все – будет отдельный параметр. Пока оставим обязательный `cell_id`).

**Экспорт состояния:**
- `async export_state() -> bytes`
  - Выгружает все переменные ядра в pickle (одним большим словарём). Это эквивалент `get_variable` для всех, но может быть оптимизировано.

**Управление жизненным циклом:**
- `async cancel_cell()`
  - Прерывает текущую выполняемую операцию в ядре (отправляет `{"cmd":"interrupt","kernel_id":"..."}`). Ядро остаётся активным.
- `async shutdown_kernel()`
  - Уничтожает ядро (состояние теряется), но контейнер и файлы сохраняются. Сессия может быть переиспользована с новым ядром (метод `restart_kernel()`? Позже).
- `async terminate()`
  - Полное удаление: уничтожает ядро, а если в контейнере не осталось ядер – запускает таймер на idle_ttl или немедленно останавливает контейнер (зависит от настроек). Сама сессия удаляется из менеджера.

**TTL:**
- Внутренний метод `_check_ttl()` – вызывается периодически менеджером. Если `ttl` задан и время последней активности истекло, сессия завершается (вызов `terminate()`).

### 6. Компонент: KernelOrchestrator (внутренний скрипт)

Скрипт `kernel_orchestrator.py` запускается внутри контейнера с python и должен:

- Импортировать стандартный `ipykernel` и `jupyter_client`.
- Управлять пулом ядер, где каждое ядро – это отдельный процесс `ipykernel_launcher`, подключённый через unix-сокет (или TCP на localhost, если unix-сокеты недоступны).
- Предоставлять JSON-RPC интерфейс через stdin/stdout.

#### Детали реализации
- При запуске читает конфигурацию из переменных окружения (например, `SANDBOX_WORKSPACE`).
- Создаёт рабочий каталог для connection файлов (например, `/tmp/kernels`).
- Хранит `kernels: Dict[str, KernelEntry]`, где `KernelEntry` содержит:
  - `process: subprocess.Popen`
  - `client: jupyter_client.BlockingKernelClient` (обёрнутый в асинхронный вызов через потоки или asyncio.to_thread)
- Команды:

  - **create_kernel**
    - Запрос: `{"cmd":"create_kernel"}`
    - Действие: генерирует уникальный `kernel_id`, создаёт connection file, запускает процесс ядра, ожидает его готовности, создаёт клиент и сохраняет в пул.
    - Ответ: `{"kernel_id": "..."}`

  - **destroy_kernel**
    - Запрос: `{"cmd":"destroy_kernel","kernel_id":"..."}`
    - Действие: останавливает ядро, удаляет процесс и клиент.
    - Ответ: `{"status":"ok"}`

  - **execute**
    - Запрос: `{"cmd":"execute","kernel_id":"...","cell_id":"...","code":"...","timeout":30}`
    - Действие: отправляет код в ядро через `client.execute(code)`, собирает сообщения: stdout, stderr, display_data (изображения), ошибки. Изображения (MIME base64) сохраняются во внутренний словарь `images[cell_id] = [...]`. Возвращает только метаданные изображений (id, формат).
    - Ответ: `{"status":"ok","stdout":"...","stderr":"...","images":[{"id":"img1","format":"png"}],"error":null}` или `{"status":"timeout"}` при превышении таймаута. Таймаут реализуется через обрыв выполнения: посылается `interrupt`, и если за короткое время не завершается – жесткое завершение ядра с ошибкой.

  - **get_variables**
    - Запрос: `{"cmd":"get_variables","kernel_id":"..."}`
    - Действие: в ядре выполняется код, который собирает имена и типы переменных из `globals()`, исключая служебные (начинающиеся с подчёркивания). Для каждого получает примерный размер (sys.getsizeof). Возвращает список объектов.
    - Ответ: `{"variables":[{"name":"x","type":"int","size":28}]}`

  - **get_variable**
    - Запрос: `{"cmd":"get_variable","kernel_id":"...","name":"x"}`
    - Действие: извлекает переменную через `globals()[name]`, сериализует pickle.dumps, кодирует base64.
    - Ответ: `{"pickle":"base64encodedstring"}`

  - **get_images**
    - Запрос: `{"cmd":"get_images","kernel_id":"...","cell_id":"..."}`
    - Действие: возвращает список изображений с данными (base64) для указанной ячейки. После возврата можно очистить хранилище для этого cell_id.
    - Ответ: `{"images":[{"id":"img1","format":"png","data":"base64..."}]}`

  - **list_files**
    - Запрос: `{"cmd":"list_files","path":"."}`
    - Действие: рекурсивно или нет? (Ограничимся одним уровнем для безопасности). Возвращает список файлов и папок.
    - Ответ: `{"files":[{"name":"notebook.ipynb","type":"file","size":1234}]}`

  - **read_file**
    - Запрос: `{"cmd":"read_file","path":"notebook.ipynb"}`
    - Действие: читает файл из рабочей директории, возвращает содержимое в base64.
    - Ответ: `{"content":"base64..."}`

  - **write_file**
    - Запрос: `{"cmd":"write_file","path":"data.csv","content":"base64..."}`
    - Действие: записывает файл.
    - Ответ: `{"status":"ok"}`

  - **shutdown**
    - Запрос: `{"cmd":"shutdown"}`
    - Действие: останавливает все ядра, завершает процесс оркестратора.
    - Ответ: `{"status":"ok"}` перед выходом.

- Взаимодействие с ядром: используем `jupyter_client.BlockingKernelClient` в отдельном потоке для каждого ядра, чтобы не блокировать основной event loop оркестратора. Для асинхронной обёртки можно применить `asyncio.to_thread` или пул потоков.

### 7. Компонент: GVisorProvider

- Отвечает за запуск контейнера с помощью `runsc`.
- `async start(overlay_lowerdir: str, workspace_path: str, cpu_limit: float = 1.0, memory_limit_mb: int = 512) -> (asyncio.subprocess.Process, stdin, stdout)`
  - Формирует команду `runsc do --rootless --network=none --cpu=<...> --memory=<...> --overlay-lowerdir=<lower> --overlay-upperdir=<workspace>/upper --overlay-workdir=<workspace>/work -- python -m sandbox.kernel_orchestrator`
  - Запускает процесс, возвращает stdin/stdout как `asyncio.StreamWriter`/`StreamReader` (или proc.stdin/stdout).
- `async stop(process: asyncio.subprocess.Process)` – отправляет SIGTERM, ожидает завершения.
- `async interrupt(process)` – отправляет SIGINT.

Параметры overlay: gVisor поддерживает опцию `--overlay-lowerdir` для монтирования read-only слоя, плюс `--overlay-upperdir` и `--overlay-workdir` для верхнего слоя. Это делается через OCI-конфигурацию или прямо через runsc (проверить возможности runsc).

### 8. Компонент: VenvStorage

- Хранит виртуальные окружения по пути `<storage_path>/<venv_hash>/`.
- `async get_or_create(venv_name: str = None, requirements: List[str] = None) -> str` (возвращает путь к venv).
  - Если venv_name передан, ищет папку с таким именем (или хэшем). Если нет, создаёт через `uv venv` и `uv pip install` в этот каталог.
  - Если передан список требований, вычисляет SHA256 хэш от их отсортированного списка, ищет по хэшу. При отсутствии создаёт окружение.
- `async build_venv(requirements: List[str]) -> str` – создаёт новый venv через `uv`, возвращает путь.
- Можно добавить блокировку, чтобы несколько одновременных запросов на одно окружение не создавали его дважды.

### 9. Управление ячейками (CellInfo)

`CellInfo` – это dataclass:
```python
@dataclass
class CellInfo:
    cell_id: str
    cell_type: str  # "code" или "markdown"
    source: str
    origin: str     # "original" или "added"
    metadata: dict
```

- Парсинг ноутбука: функция `parse_notebook(ipynb_json: dict) -> List[CellInfo]` извлекает ячейки из ipynb формата (v4+). Для каждой code/markdown ячейки генерирует `cell_id` на основе UUID, либо использует существующий из метаданных (`cell.metadata.id` если есть). `origin = "original"`.

### 10. Безопасность и ограничения

- Сеть в контейнере полностью отключена (`--network=none`). Связь между оркестратором и ядрами через unix-сокеты.
- Доступ к файловой системе ограничен workspace (верхним слоем overlay). Нижний слой venv монтируется read-only.
- Ресурсы CPU и памяти ограничиваются через runsc параметры.
- Пользователь внутри контейнера – непривилегированный.
- Белый список модулей Python пока не реализуется.
- При сериализации переменных pickle, во избежание инъекций, объекты проверяются на отсутствие `code` объектов? Оставим на будущее, так как среда изолирована.

### 11. Жизненный цикл и TTL

- **Сессия**: создаётся с опциональным `ttl`. После последней активности (вызова любого метода, изменяющего состояние) запускается таймер. Менеджер проверяет каждые `container_cleanup_interval` секунд и завершает просроченные сессии.
- **Контейнер**: не имеет собственного TTL, но уничтожается фоновой задачей менеджера, если `active_kernels == 0` и прошло `container_idle_ttl` секунд с момента последней активности (или с момента удаления последнего ядра). Это позволяет быстро переиспользовать контейнеры без повторной инициализации overlay.

### 12. Обработка ошибок и таймаутов

- `execute_cell`/`execute_code` принимает `timeout`. Если выполнение превышает таймаут, оркестратор прерывает ядро (interrupt), затем выжидает 5 секунд; если код не завершился, убивает ядро и возвращает `{"status":"timeout"}`. В этом случае ядро становится нерабочим, сессия должна быть пересоздана (или вызван `shutdown_kernel` и новое ядро).
- `cancel_cell` посылает прерывание, но не убивает ядро.
- Любые ошибки протокола (невалидный JSON, потеря соединения) должны пробрасываться как исключения `SandboxError`.

### 13. Зависимости

- Python 3.11+
- `ipykernel`
- `jupyter_client`
- `nbformat` (для парсинга ipynb)
- `dill` или стандартный `pickle`
- `uv` (для сборки venv)
- `runsc` (gVisor) должен быть установлен в системе и доступен в PATH.

### 14. Тестирование

- Модульные тесты на все компоненты (с моками контейнеров и ядер).
- Интеграционные тесты с реальным gVisor (или Docker с подходящим профилем безопасности как запасной вариант).
- Тесты на сценарии: загрузка ноутбука, выполнение ячеек в разном порядке, захват переменных, изображений, таймауты, отмену, TTL, переиспользование контейнеров.

### 15. Пример использования (повтор для полноты)

```python
import asyncio
from sandbox import SandboxManager

async def main():
    manager = SandboxManager(isolation="gvisor", venv_storage="USER_HOME.sandbox_data/venvs")

    # Создание сессии
    session = await manager.create_session(
        venv_name="datascience-py311",
        ttl=600
    )

    # Загрузка ноутбука
    with open("notebook.ipynb", "rb") as f:
        await session.upload_file("notebook.ipynb", f.read())

    cells = await session.open_notebook("notebook.ipynb")

    for cell in cells:
        if cell.cell_type == "code":
            result = await session.execute_cell(cell.cell_id, timeout=10)
            print(result.stdout)
            if result.images:
                imgs = await session.get_images(cell.cell_id)
                # обработка изображений

    # Интерактив
    new_id = await session.add_cell("x = 42")
    await session.execute_cell(new_id)

    vars_ = await session.list_variables()
    print(vars_)

    await session.terminate()
    await manager.shutdown()

asyncio.run(main())
```

### 16. Дальнейшие шаги по реализации

1. Реализовать `VenvStorage` с использованием `uv`.
2. Реализовать `GVisorProvider` (запуск контейнера с overlay).
3. Написать `kernel_orchestrator.py` с поддержкой всех команд.
4. Реализовать `Container` с асинхронным протоколом.
5. Реализовать `SandboxSession` с логикой ячеек и выполнением.
6. Реализовать `SandboxManager` с пулом контейнеров и TTL.
7. Покрыть тестами.
8. Предоставить документацию.

Данное ТЗ должно быть достаточным для начала кодирования AI-агентами. При возникновении дополнительных вопросов в процессе имплементации можно обращаться за уточнениями.