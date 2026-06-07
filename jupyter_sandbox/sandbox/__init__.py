"""
Sandbox — безопасное выполнение Jupyter-ноутбуков в изолированных окружениях.
"""

__version__ = "0.1.0"

from .session import SandboxSession
from .manager import SandboxManager
from .models import CellInfo, CellResult
from .errors import SandboxError

__all__ = [
    "SandboxManager",
    "SandboxSession",
    "CellInfo",
    "CellResult",
    "SandboxError",
]
