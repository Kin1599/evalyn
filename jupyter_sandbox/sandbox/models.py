"""
Модели данных — dataclasses для структур данных библиотеки.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class CellInfo:
    """Информация об одной ячейке ноутбука."""
    cell_id: str
    cell_type: str  # "code" или "markdown"
    source: str
    origin: str = "original"  # "original" или "added"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CellResult:
    """Результат выполнения ячейки."""
    cell_id: str
    stdout: str = ""
    stderr: str = ""
    images: List[Dict[str, str]] = field(default_factory=list)  # [{"id": "img1", "format": "png"}, ...]
    error: Optional[Dict[str, Any]] = None
    status: str = "ok"  # "ok", "timeout", "error"


@dataclass
class ImageData:
    """Данные изображения."""
    image_id: str
    format: str  # "png", "jpeg", "svg+xml"
    data: bytes


@dataclass
class VariableMeta:
    """Метаданные переменной."""
    name: str
    type_name: str
    size_bytes: int


@dataclass
class ProcessInfo:
    """Информация о процессе ядра."""
    kernel_id: str
    pid: Optional[int] = None
    creation_time: Optional[float] = None
