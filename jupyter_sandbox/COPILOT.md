# Инструкции для агентов

## Окружение разработки

- **Текущий shell**: PowerShell (`pwsh`)
- **Язык**: Python 3.11.4
- **Пакетный менеджер**: uv (установлен)
- **Виртуальное окружение**: `.venv` (создано с помощью `uv venv`)

## Активация окружения

```powershell
.venv\Scripts\Activate.ps1
```

## Git Bash команды в PowerShell
Пути регистрозависмые, поэтому диск E а не е
Если нужны команды из Git Bash, добавляй `.exe` расширение например:
- `cat.exe` вместо `cat`
- `grep.exe` вместо `grep`
- `sed.exe` вместо `sed`
- `ls.exe` вместо `ls`

Пример:
```powershell
cat.exe README.md
grep.exe "pattern" file.txt
```

## Основные команды проекта

```powershell
# Установка зависимостей
uv sync

# Запуск тестов
python -m pytest tests/ -v

# Форматирование кода
black sandbox/

# Линтинг
ruff check sandbox/

# Проверка типов
mypy sandbox/

# Запуск конкретного теста
python -m pytest tests/test_container.py -v
```

## Структура проекта

- `sandbox/` - основной код пакета
- `tests/` - тесты
- `examples/` - примеры использования
- `docs/` - документация
- `pyproject.toml` - конфигурация проекта