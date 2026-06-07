"""
Исключения и ошибочные состояния.
"""


class SandboxError(Exception):
    """Базовое исключение для всех ошибок Sandbox."""
    pass


class ContainerError(SandboxError):
    """Ошибка управления контейнером."""
    pass


class KernelError(SandboxError):
    """Ошибка выполнения ядра."""
    pass


class TimeoutError(SandboxError):
    """Таймаут выполнения."""
    pass


class VenvBuildError(SandboxError):
    """Ошибка при сборке виртуального окружения."""
    pass


class ProtocolError(SandboxError):
    """Ошибка протокола взаимодействия с контейнером."""
    pass
