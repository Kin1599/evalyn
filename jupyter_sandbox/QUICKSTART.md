# 🚀 QUICKSTART — Как начать разработку

**Состояние:** ✅ Этап 1 (Фундамент) завершён. Структура проекта готова.

---

## 📋 Текущее состояние

- ✅ Структура проекта создана
- ✅ Все dataclasses и исключения определены
- ✅ Утилиты реализованы
- ✅ Базовые tests написаны
- ✅ Документация подготовлена
- ✅ Примеры использования созданы

**Проверка Этапа 1:**

```bash
cd e:\hw_checker\sandbox
pytest tests/test_models.py -v
```

**Результат:** Все тесты должны пройти ✅

---

## 🎯 Следующие шаги (Этап 2: Провайдеры)

### 2.1 Реализовать VenvStorage

**Файл:** `sandbox/venv_storage.py`

**Задачи:**
1. Класс `VenvStorage` с методом `get_or_create(venv_name, requirements)`
2. Использование `uv venv` для создания окружений
3. Кэширование по хэшу требований
4. Блокировка для предотвращения дублирования
5. Тесты в `tests/test_venv_storage.py` (с моками `subprocess`)

**Примерный код:**

```python
from pathlib import Path
import hashlib
import asyncio
from typing import Optional, List
from .utils import hash_requirements, ensure_dir

class VenvStorage:
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self._locks = {}  # Блокировки для каждого venv_hash
    
    async def get_or_create(
        self,
        venv_name: Optional[str] = None,
        requirements: Optional[List[str]] = None
    ) -> str:
        """Получить или создать venv. Возвращает путь."""
        if venv_name:
            venv_hash = venv_name
        elif requirements:
            venv_hash = hash_requirements(requirements)
        else:
            raise ValueError("Передайте venv_name или requirements")
        
        venv_path = self.storage_path / venv_hash
        
        # Блокировка для этого venv_hash
        if venv_hash not in self._locks:
            self._locks[venv_hash] = asyncio.Lock()
        
        async with self._locks[venv_hash]:
            # Проверить, существует ли venv
            if venv_path.exists():
                return str(venv_path)
            
            # Создать новый venv
            await ensure_dir(venv_path)
            if requirements:
                await self._build_venv(venv_path, requirements)
            else:
                # По умолчанию venv с базовыми пакетами
                await self._build_venv(venv_path, [])
            
            return str(venv_path)
    
    async def _build_venv(self, path: Path, requirements: List[str]) -> None:
        """Собрать venv используя uv."""
        # Примерно: uv venv <path> && uv pip install -r requirements.txt
        pass
```

### 2.2 Реализовать GVisorProvider

**Файл:** `sandbox/gvisor_provider.py`

**Задачи:**
1. Класс `GVisorProvider` с методом `start(overlay_lowerdir, workspace_path, ...)`
2. Запуск `runsc do` с параметрами overlay и ресурсов
3. Возврат процесса и его stdin/stdout
4. Метод `stop()` для остановки
5. Тесты в `tests/test_gvisor_provider.py` (с моками `asyncio.subprocess`)

**Примерный код:**

```python
import asyncio
from pathlib import Path

class GVisorProvider:
    async def start(
        self,
        overlay_lowerdir: str,
        workspace_path: str,
        cpu_limit: float = 1.0,
        memory_limit_mb: int = 512
    ):
        """Запустить контейнер гVisor."""
        # Формируем команду:
        # runsc do \
        #   --rootless \
        #   --network=none \
        #   --cpu=<cpu_limit> \
        #   --memory=<memory_limit_mb> \
        #   --overlay-lowerdir=<lower> \
        #   --overlay-upperdir=<workspace>/upper \
        #   --overlay-workdir=<workspace>/work \
        #   -- python -m sandbox.kernel_orchestrator
        
        cmd = [
            "runsc", "do",
            "--rootless",
            "--network=none",
            f"--cpu={cpu_limit}",
            f"--memory={memory_limit_mb}m",
            f"--overlay-lowerdir={overlay_lowerdir}",
            f"--overlay-upperdir={workspace_path}/upper",
            f"--overlay-workdir={workspace_path}/work",
            "--",
            "python", "-m", "sandbox.kernel_orchestrator"
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        return process
    
    async def stop(self, process: asyncio.subprocess.Process):
        """Остановить процесс."""
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
```

### 2.3 Написать тесты

**Файлы:**
- `tests/test_venv_storage.py` — unit-тесты VenvStorage
- `tests/test_gvisor_provider.py` — unit-тесты GVisorProvider

**Пример теста:**

```python
# tests/test_venv_storage.py
import pytest
from unittest.mock import patch, AsyncMock
from sandbox.venv_storage import VenvStorage

@pytest.mark.asyncio
async def test_get_or_create_with_name():
    storage = VenvStorage("/tmp/venvs")
    
    with patch("pathlib.Path.exists", return_value=True):
        result = await storage.get_or_create(venv_name="default")
        assert result == "/tmp/venvs/default"

@pytest.mark.asyncio
async def test_get_or_create_with_requirements():
    storage = VenvStorage("/tmp/venvs")
    reqs = ["numpy", "pandas"]
    
    # Mock subprocess
    with patch.object(storage, "_build_venv", new_callable=AsyncMock):
        result = await storage.get_or_create(requirements=reqs)
        # Должен быть вызван _build_venv
        storage._build_venv.assert_called_once()
```

---

## 🔧 Инструменты и проверки

### Запуск тестов после каждого компонента

```bash
# Тесты Этапа 1 (уже готовы)
pytest tests/test_models.py -v

# Тесты Этапа 2 (когда будут реализованы)
pytest tests/test_venv_storage.py -v
pytest tests/test_gvisor_provider.py -v

# Все тесты
pytest tests/ -v

# С coverage
pytest tests/ --cov=sandbox --cov-report=html
```

### Проверка типов

```bash
mypy sandbox/ --ignore-missing-imports
```

### Форматирование и линтинг

```bash
# Форматирование (black)
black sandbox/ tests/

# Проверка качества кода (ruff)
ruff check sandbox/

# Все вместе
black sandbox/ tests/
ruff check sandbox/
```

---

## 📚 Структура работы

Для каждого компонента:

1. **Определить интерфейс** (signature методов)
2. **Написать тесты** (TDD подход)
3. **Реализовать компонент**
4. **Запустить тесты** (должны пройти)
5. **Код-ревью** (проверить качество)
6. **Обновить документацию** (примеры, комментарии)

---

## 📖 Полезная информация

### Где читать про каждый компонент

| Компонент | План | Архитектура | API |
|-----------|------|-------------|-----|
| VenvStorage | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md#этап-2-провайдеры) | [architecture.md](docs/architecture.md#2-venvstrage) | [api.md](docs/api.md) |
| GVisorProvider | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md#этап-2-провайдеры) | [architecture.md](docs/architecture.md#5-gvsorprovider) | [api.md](docs/api.md) |
| Container | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md#этап-4-контейнеры-и-менеджер) | [architecture.md](docs/architecture.md#2-container) | [api.md](docs/api.md) |
| SandboxManager | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md#этап-4-контейнеры-и-менеджер) | [architecture.md](docs/architecture.md#1-sandboxmanager) | [api.md](docs/api.md) |
| SandboxSession | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md#этап-5-сессии-и-интеграция) | [architecture.md](docs/architecture.md#3-sandboxsession) | [api.md](docs/api.md) |
| KernelOrchestrator | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md#этап-3-kernelorchestrater) | [architecture.md](docs/architecture.md#4-kernelorchestrater) | [api.md](docs/api.md) |

### Примеры использования

- [examples/basic_usage.py](examples/basic_usage.py) — базовый сценарий
- [examples/notebook_execution.py](examples/notebook_execution.py) — выполнение ноутбука

### Документация

- [README.md](README.md) — обзор проекта
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) — этап-за-этапом разбор
- [PROJECT_STRUCTURE.txt](PROJECT_STRUCTURE.txt) — визуальная структура
- [docs/architecture.md](docs/architecture.md) — архитектура
- [docs/api.md](docs/api.md) — полный API reference
- [docs/installation.md](docs/installation.md) — установка

---

## ✅ Чек-лист перед коммитом Этапа 2

- [ ] VenvStorage реализован
- [ ] GVisorProvider реализован
- [ ] Все тесты пройдены (`pytest tests/ -v`)
- [ ] Код отформатирован (`black sandbox/`)
- [ ] Linting пройден (`ruff check sandbox/`)
- [ ] Type-checking пройден (`mypy sandbox/`)
- [ ] Обновлена документация (примеры, комментарии)
- [ ] Создан pull request с описанием

---

## 🎓 Читать дальше

После завершения Этапа 2 переходим к **Этапу 3: KernelOrchestrator**.

Каждый этап увеличивает функциональность и готовность проекта.

```
Этап 1 ✅ → Этап 2 ⏳ → Этап 3 ⏳ → Этап 4 ⏳ → Этап 5 ⏳
```

---

**Вопросы?** Обратитесь к [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) или [docs/](docs/).
