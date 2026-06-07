# API Reference — Полная документация

## SandboxManager

Главная точка входа библиотеки.

### Конструктор

```python
class SandboxManager:
    def __init__(
        self,
        isolation: str = "gvisor",
        venv_storage_path: str = "USER_HOME.sandbox_data/venvs",
        container_idle_ttl: int = 300,
        container_max_kernels: int = 10,
        container_cleanup_interval: int = 60,
    ):
        """
        Инициализирует менеджер.

        Args:
            isolation: "gvisor" или будущие варианты
            venv_storage_path: путь к хранилищу окружений
            container_idle_ttl: время жизни контейнера без ядер (сек)
            container_max_kernels: макс. ядер в одном контейнере
            container_cleanup_interval: интервал очистки (сек)
        """
```

### Методы

#### create_session

```python
async def create_session(
    self,
    venv_name: Optional[str] = None,
    requirements: Optional[List[str]] = None,
    ttl: Optional[int] = None,
    files: Optional[Dict[str, bytes]] = None,
) -> SandboxSession:
    """
    Создаёт новую сессию.

    Args:
        venv_name: имя предсуществующего окружения
        requirements: список требований pip
        ttl: таймаут неактивности сессии (сек)
        files: начальные файлы {'filename': b'content'}

    Returns:
        SandboxSession готовая к использованию

    Raises:
        VenvBuildError: если окружение не найдено и не создано
        ContainerError: если контейнер не запущен
    """
```

- **Логика:** 
  1. Вычисляет `venv_hash` (по имени и requirements)
  2. Ищет контейнер с `venv_hash` и доступным слотом для ядра
  3. Если контейнер не найден, создаёт новый
  4. В контейнере создаёт новое ядро
  5. Оборачивает в `SandboxSession`, загружает файлы

#### get_session

```python
async def get_session(self, session_id: str) -> Optional[SandboxSession]:
    """Получить активную сессию по ID."""
```

#### shutdown_container

```python
async def shutdown_container(self, container_id: str) -> None:
    """Принудительно остановить контейнер и все его ядра."""
```

#### shutdown

```python
async def shutdown(self) -> None:
    """Завершить все сессии и контейнеры."""
```

---

## SandboxSession

Асинхронный интерфейс для взаимодействия с ядром.

### Атрибуты

```python
session_id: str              # Уникальный UUID
kernel_id: str               # ID ядра в контейнере
container: Container         # Ссылка на контейнер
cells: Dict[str, CellInfo]  # Кэш ячеек ноутбука
```

### Методы файлов

#### upload_file

```python
async def upload_file(self, name: str, content: bytes) -> None:
    """
    Загрузить файл в контейнер.

    Args:
        name: имя файла (относительный путь)
        content: содержимое

    Raises:
        SandboxError: если запись не удалась
    """
```

#### get_file

```python
async def get_file(self, name: str) -> bytes:
    """
    Получить файл из контейнера.

    Args:
        name: имя файла

    Returns:
        содержимое в виде bytes

    Raises:
        SandboxError: если файл не найден
    """
```

#### list_files

```python
async def list_files(self) -> List[str]:
    """Список файлов в рабочей директории контейнера."""
```

### Методы ячеек и выполнения

#### open_notebook

```python
async def open_notebook(self, filename: str) -> List[CellInfo]:
    """
    Открыть Jupyter-ноутбук и парсить ячейки.

    Args:
        filename: имя .ipynb файла

    Returns:
        Список CellInfo (code и markdown ячейки)

    Raises:
        SandboxError: если файл не найден или некорректен
    """
```

#### add_cell

```python
async def add_cell(
    self, 
    code: str, 
    origin: str = "added"
) -> str:
    """
    Добавить новую code-ячейку.

    Args:
        code: исходный код
        origin: "added" (или другой маркер источника)

    Returns:
        cell_id новой ячейки
    """
```

#### list_cells

```python
async def list_cells(self) -> List[CellInfo]:
    """Получить все ячейки (code и markdown)."""
```

#### get_cell

```python
async def get_cell(self, cell_id: str) -> CellInfo:
    """Получить информацию об одной ячейке."""
```

#### execute_cell

```python
async def execute_cell(
    self,
    cell_id: str,
    timeout: Optional[int] = None,
) -> CellResult:
    """
    Выполнить code-ячейку.

    Args:
        cell_id: ID ячейки (из open_notebook или add_cell)
        timeout: таймаут выполнения (сек)

    Returns:
        CellResult с stdout, stderr, изображениями, ошибками

    Raises:
        TimeoutError: если превышен timeout
        KernelError: если ядро упало
    """
```

#### execute_code

```python
async def execute_code(
    self,
    code: str,
    timeout: Optional[int] = None,
) -> CellResult:
    """
    Выполнить произвольный код без привязки к ячейке.

    Args:
        code: исходный код
        timeout: таймаут (сек)

    Returns:
        CellResult
    """
```

### Методы переменных

#### list_variables

```python
async def list_variables(self) -> List[VariableMeta]:
    """
    Получить список переменных в глобальном пространстве ядра.

    Returns:
        Список VariableMeta(name, type_name, size_bytes)

    Note:
        Служебные переменные (начинающиеся с _) исключены.
    """
```

#### get_variable

```python
async def get_variable(self, name: str) -> bytes:
    """
    Получить переменную в виде pickle-сериализованных bytes.

    Args:
        name: имя переменной

    Returns:
        pickle.dumps(value) — может быть декодировано как pickle.loads()

    Raises:
        SandboxError: если переменная не найдена или не сериализуется
    """
```

#### export_state

```python
async def export_state(self) -> bytes:
    """
    Экспортировать всё глобальное состояние ядра.

    Returns:
        pickle.dumps(globals_dict)

    Note:
        Включает все переменные, импортированные модули и функции.
    """
```

### Методы изображений

#### get_images

```python
async def get_images(
    self, 
    cell_id: Optional[str] = None
) -> List[dict]:
    """
    Получить все изображения из ячейки.

    Args:
        cell_id: ID ячейки (если None, последняя выполненная)

    Returns:
        Список {'id', 'format' (png/jpeg/svg+xml), 'data' (base64 bytes)}

    Note:
        После успешного возврата изображения могут быть очищены на сервере.
    """
```

### Методы управления

#### cancel_cell

```python
async def cancel_cell(self) -> None:
    """
    Прерать текущее выполнение кода (Ctrl+C в ядре).

    Note:
        Ядро остаётся активным и может выполнять новый код.
    """
```

#### shutdown_kernel

```python
async def shutdown_kernel(self) -> None:
    """
    Остановить ядро (состояние теряется).

    Note:
        Контейнер и файлы остаются. Сессию можно переиспользовать
        с новым ядром (требуется `restart_kernel()`).
    """
```

#### terminate

```python
async def terminate(self) -> None:
    """
    Полное завершение сессии.

    Закрывает ядро, и если контейнер пуст, его останавливает.
    Сессия удаляется из менеджера.
    """
```

---

## Модели данных

### CellInfo

```python
@dataclass
class CellInfo:
    cell_id: str                    # Уникальный ID
    cell_type: str                  # "code" или "markdown"
    source: str                     # Исходный текст
    origin: str = "original"        # "original" или "added"
    metadata: Dict[str, Any] = ...  # Метаданные из .ipynb
```

### CellResult

```python
@dataclass
class CellResult:
    cell_id: str
    stdout: str = ""
    stderr: str = ""
    images: List[Dict[str, str]] = []  # [{"id": "...", "format": "..."}]
    error: Optional[Dict[str, Any]] = None
    status: str = "ok"  # "ok", "timeout", "error"
```

### VariableMeta

```python
@dataclass
class VariableMeta:
    name: str
    type_name: str      # "int", "list", "module", ...
    size_bytes: int     # sys.getsizeof()
```

### ImageData

```python
@dataclass
class ImageData:
    image_id: str
    format: str         # "png", "jpeg", "svg+xml"
    data: bytes         # base64 декодированные данные
```

---

## Исключения

```python
class SandboxError(Exception):
    """Базовое исключение."""

class ContainerError(SandboxError):
    """Ошибка контейнера."""

class KernelError(SandboxError):
    """Ошибка ядра."""

class TimeoutError(SandboxError):
    """Таймаут выполнения."""

class VenvBuildError(SandboxError):
    """Ошибка сборки окружения."""

class ProtocolError(SandboxError):
    """Ошибка протокола взаимодействия."""
```

---

## Примеры

### Базовый сценарий

```python
import asyncio
from sandbox import SandboxManager

async def main():
    manager = SandboxManager()
    
    # Создать сессию
    session = await manager.create_session(
        venv_name="default",
        ttl=600  # 10 минут
    )
    
    # Выполнить код
    result = await session.execute_code("x = 42\nprint(x)", timeout=5)
    print(result.stdout)  # "42"
    
    # Получить переменные
    vars_ = await session.list_variables()
    print(vars_)
    
    # Завершить
    await session.terminate()
    await manager.shutdown()

asyncio.run(main())
```

### Выполнение ноутбука

```python
async def execute_notebook():
    manager = SandboxManager()
    session = await manager.create_session(
        requirements=["numpy", "pandas"]
    )
    
    # Загрузить ноутбук
    notebook_bytes = open("analysis.ipynb", "rb").read()
    await session.upload_file("analysis.ipynb", notebook_bytes)
    
    # Выполнить ячейки по порядку
    cells = await session.open_notebook("analysis.ipynb")
    for cell in cells:
        if cell.cell_type == "code":
            result = await session.execute_cell(cell.cell_id, timeout=30)
            
            if result.status != "ok":
                print(f"Ошибка в {cell.cell_id}: {result.error}")
                break
            
            if result.images:
                images = await session.get_images(cell.cell_id)
                print(f"Получено {len(images)} изображений")
    
    await session.terminate()
    await manager.shutdown()
```

### Обработка ошибок

```python
async def with_error_handling():
    manager = SandboxManager()
    session = None
    
    try:
        session = await manager.create_session(
            requirements=["invalid_package_12345"]
        )
    except VenvBuildError as e:
        print(f"Не удалось собрать окружение: {e}")
        return
    
    try:
        result = await session.execute_code("1/0", timeout=5)
    except TimeoutError:
        print("Код выполнялся слишком долго")
        await session.cancel_cell()
    except KernelError as e:
        print(f"Ядро упало: {e}")
    finally:
        if session:
            await session.terminate()
        await manager.shutdown()
```
