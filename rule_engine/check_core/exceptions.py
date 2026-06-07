"""
Базовые исключения библиотеки Check Core.
"""

class CheckCoreError(Exception):
    """Базовое исключение для всех ошибок библиотеки."""
    pass


class SandboxError(CheckCoreError):
    """Ошибка при работе с песочницей (запуск, таймаут, контейнер)."""
    pass


class ResolutionError(CheckCoreError):
    """Не удалось найти переменную по InputSpec."""
    pass


class CheckConditionError(CheckCoreError):
    """Ошибка при выполнении условия проверки."""
    pass


class LLMServiceError(CheckCoreError):
    """Ошибка при обращении к LLM."""
    pass