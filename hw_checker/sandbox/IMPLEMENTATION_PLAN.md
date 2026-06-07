# План реализации — 5 этапов

Этот документ описывает разбиение проекта Sandbox на 5 управляемых этапов. Каждый этап включает компоненты, которые можно разработать и протестировать независимо, с постепенной интеграцией.

---

## 📋 Обзор этапов

| Этап | Название | Компоненты | Приблизительный объём |
|------|----------|-----------|----------------------|
| 1 | Фундамент | models, errors, utils | **~200 строк** |
| 2 | Провайдеры | venv_storage, gvisor_provider | **~500 строк** |
| 3 | KernelOrchestrator | kernel_orchestrator.py | **~800 строк** |
| 4 | Контейнеры и менеджер | container, manager | **~600 строк** |
| 5 | Сессии и интеграция | session, тесты, документация | **~700 строк** |

**Итого:** ~2.8K строк кода + тесты и документация

---

## Этап 1: Фундамент ✅ (ГОТОВ)

### Задачи
- [x] Определить dataclasses: `CellInfo`, `CellResult`, `ImageData`, `VariableMeta`
- [x] Определить исключения: `SandboxError`, `ContainerError`, `KernelError` и др.
- [x] Реализовать утилиты: `generate_id()`, `hash_requirements()`, `parse_json_line()`
- [x] Написать базовые тесты для моделей и утилит

### Файлы
- `sandbox/models.py` — dataclasses ✅
- `sandbox/errors.py` — исключения ✅
- `sandbox/utils.py` — утилиты ✅
- `tests/test_models.py` — тесты для моделей ✅

### Ожидаемое состояние
Все базовые типы определены, можно импортировать из `sandbox`:
```python
from sandbox import CellInfo, CellResult, SandboxError
from sandbox.utils import generate_id
```

---

## Этап 2: Провайдеры

### Задачи
- [ ] **VenvStorage** — управление виртуальными окружениями
  - [ ] Метод `get_or_create(venv_name, requirements)` — создание/поиск venv
  - [ ] Использование `uv venv` и `uv pip install`
  - [ ] Кэширование по хэшу требований
  - [ ] Блокировка для предотвращения дублирования
  
- [ ] **GVisorProvider** — интерфейс к runsc
  - [ ] Метод `start()` — запуск контейнера с overlay
  - [ ] Метод `stop()` — остановка контейнера
  - [ ] Асинхронное управление процессом
  - [ ] Передача параметров: горячие слои, CPU, память

### Файлы
- `sandbox/venv_storage.py` — управление окружениями
- `sandbox/gvisor_provider.py` — адаптер runsc
- `tests/test_venv_storage.py` — тесты VenvStorage (с моками)
- `tests/test_gvisor_provider.py` — тесты GVisorProvider (с моками runsc)

### Прототипные интерфейсы
```python
class VenvStorage:
    async def get_or_create(self, venv_name: str = None, 
                           requirements: List[str] = None) -> str:
        """Возвращает путь к venv."""
        pass

class GVisorProvider:
    async def start(self, overlay_lowerdir: str, workspace_path: str,
                   cpu_limit: float = 1.0, 
                   memory_limit_mb: int = 512) -> Process:
        """Запускает контейнер, возвращает процесс."""
        pass
```

---

## Этап 3: KernelOrchestrator

### Задачи
- [ ] Реализовать главный цикл оркестратора
  - [ ] Чтение команд из stdin (JSON-RPC)
  - [ ] Маршрутизация команд по kernel_id
  - [ ] Отправка ответов в stdout

- [ ] Команда `create_kernel`
  - [ ] Запуск ipykernel в отдельном процессе
  - [ ] Создание connection file
  - [ ] Инициализация jupyter_client.BlockingKernelClient

- [ ] Команда `execute`
  - [ ] Отправка кода в ядро
  - [ ] Сбор stdout, stderr
  - [ ] Захват display_data (изображения)
  - [ ] Обработка таймаутов и interrupt

- [ ] Команду `get_variables`
  - [ ] Парсинг globals() ядра
  - [ ] Сбор имён, типов, размеров переменных

- [ ] Команду `get_variable`
  - [ ] Сериализация pickle
  - [ ] Кодирование base64

- [ ] Команда `list_files`, `read_file`, `write_file`
  - [ ] Работа с файловой системой контейнера

- [ ] Команда `shutdown`
  - [ ] Корректная остановка всех ядер

### Файлы
- `sandbox/kernel_orchestrator.py` — основной скрипт
- `tests/test_kernel_orchestrator.py` — модульные тесты (с моками ipykernel)

### Ожидаемое состояние
Скрипт можно запустить как:
```bash
python -m sandbox.kernel_orchestrator
```
И общаться с ним через stdin/stdout json-командами.

---

## Этап 4: Контейнеры и менеджер

### Задачи

#### Container
- [ ] Класс `Container` — оборачивает процесс контейнера
  - [ ] Инициализация: `container_id`, `venv_hash`, `process`
  - [ ] Метод `create_kernel()` — отправляет команду, получает kernel_id
  - [ ] Метод `destroy_kernel(kernel_id)` — уничтожает ядро
  - [ ] Метод `send_command(cmd)` — JSON-RPC запрос
  - [ ] Счётчик `active_kernels`
  - [ ] `last_activity` для TTL
  - [ ] Метод `shutdown()`

#### SandboxManager
- [ ] Класс `SandboxManager` — главная точка входа
  - [ ] Инициализация параметров (isolation, venv_storage_path, TTL)
  - [ ] Пул контейнеров: `Dict[str, Container]`
  - [ ] Метод `create_session()` — выбор контейнера и создание ядра
  - [ ] Метод `get_session(session_id)`
  - [ ] Метод `shutdown_container(container_id)`
  - [ ] Метод `shutdown()` — завершение всего
  - [ ] Фоновая задача `_cleanup_loop()` — TTL контейнеров и сессий
  - [ ] Метод `_get_or_create_container()` — логика выбора контейнера

### Файлы
- `sandbox/container.py` — класс Container
- `sandbox/manager.py` — класс SandboxManager
- `tests/test_container.py` — тесты Container (с моками процессов)
- `tests/test_manager.py` — тесты SandboxManager (с моками контейнеров)

### Прототипные интерфейсы
```python
class Container:
    async def create_kernel(self) -> str: ...
    async def destroy_kernel(self, kernel_id: str) -> None: ...
    async def send_command(self, cmd: dict) -> dict: ...

class SandboxManager:
    async def create_session(self, venv_name: str = None, 
                            requirements: List[str] = None,
                            ttl: Optional[int] = None) -> SandboxSession: ...
    async def shutdown(self) -> None: ...
```

---

## Этап 5: Сессии и интеграция

### Задачи

#### SandboxSession
- [ ] Класс `SandboxSession` — интерфейс для клиента
  - [ ] Атрибуты: `session_id`, `container`, `kernel_id`, `cells`
  - [ ] Методы файлов: `upload_file()`, `get_file()`, `list_files()`
  - [ ] Методы ячеек: `open_notebook()`, `add_cell()`, `list_cells()`, `get_cell()`
  - [ ] Методы выполнения: `execute_cell()`, `execute_code()`
  - [ ] Методы переменных: `list_variables()`, `get_variable()`
  - [ ] Методы изображений: `get_images()`
  - [ ] Методы управления: `cancel_cell()`, `shutdown_kernel()`, `terminate()`
  - [ ] `_check_ttl()` — проверка таймаутов

#### Интеграция
- [ ] Интеграционные тесты всего стека
- [ ] Пример использования: базовый сценарий
- [ ] Пример использования: выполнение ноутбука
- [ ] Документирование API
- [ ] Примеры ошибок и обработки

### Файлы
- `sandbox/session.py` — класс SandboxSession
- `tests/test_session.py` — тесты SandboxSession  - `tests/test_integration.py` — интеграционные тесты
- `docs/api.md` — полная документация API
- `examples/` — примеры использования ✅

### Прототипный интерфейс
```python
class SandboxSession:
    async def execute_cell(self, cell_id: str, timeout: Optional[int] = None) -> CellResult: ...
    async def execute_code(self, code: str, timeout: Optional[int] = None) -> CellResult: ...
    async def list_variables(self) -> List[VariableMeta]: ...
    async def get_variable(self, name: str) -> bytes: ...
    async def terminate(self) -> None: ...
```

---

## 🔍 Зависимости между этапами

```
Этап 1: Фундамент
    ↓
Этап 2: Провайдеры
    ↓
Этап 3: KernelOrchestrator
    ↓
Этап 4: Container + Manager
    ↓
Этап 5: Session + Интеграция
```

Каждый этап зависит от предыдущего, но каждый может быть разработан относительно независимо внутри своей группы компонентов.

---

## 📝 Чек-лист разработки

### Перед начало каждого этапа
- [ ] Определить точные интерфейсы (сигнатуры методов)
- [ ] Написать тесты (желательно TDD)
- [ ] Наметить исходные заготовки (stubs)

### Во время разработки
- [ ] Следовать типизации (type hints)
- [ ] Использовать asyncio где требуется
- [ ] Обрабатывать исключения
- [ ] Логировать критические операции

### После каждого этапа
- [ ] Запустить тесты этапа
- [ ] Обновить документацию
- [ ] Провести review чистоты кода
- [ ] Подготовить примеры использования новых компонентов

---

## ⏱ Примерная временная оценка

| Этап | Разработка | Тестирование | Всего |
|------|-----------|--------------|-------|
| 1    | 1ч        | 1ч           | 2ч    |
| 2    | 3ч        | 2ч           | 5ч    |
| 3    | 4ч        | 3ч           | 7ч    |
| 4    | 3ч        | 2ч           | 5ч    |
| 5    | 4ч        | 4ч           | 8ч    |
| **Итого** | **15ч** | **12ч** | **27ч** |

---

## 🚀 Запуск разработки

После завершения каждого этапа можно проверить прогресс:

```bash
# Тесты этапа
pytest tests/test_models.py -v
pytest tests/test_venv_storage.py -v
# ... и т.д.

# Предварительная проверка типов
mypy sandbox/ --ignore-missing-imports

# Форматирование кода  
black sandbox/ tests/

# Проверка качества
ruff check sandbox/
```

---

## 📚 Дополнительные ресурсы

- [Архитектура](architecture.md)
- [API Reference](api.md)
- [Установка](installation.md)
- [Примеры](../examples/)
