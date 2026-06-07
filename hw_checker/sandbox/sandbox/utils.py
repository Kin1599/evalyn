"""
Утилиты и вспомогательные функции.
"""

import json
import uuid
import hashlib
from typing import List, Optional, Dict, Any
from pathlib import Path


def generate_id(prefix: str = "") -> str:
    """Генерирует уникальный ID с опциональным префиксом."""
    uid = str(uuid.uuid4())[:8]
    return f"{prefix}_{uid}" if prefix else uid


def hash_requirements(requirements: List[str]) -> str:
    """Вычисляет хэш от списка требований."""
    sorted_reqs = sorted(requirements)
    content = "\n".join(sorted_reqs)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def parse_json_line(line: str) -> Dict[str, Any]:
    """Парсит JSON-строку. Выбрасывает исключение при ошибке."""
    return json.loads(line)


def encode_json_line(data: Dict[str, Any]) -> str:
    """Кодирует данные в JSON-строку с newline."""
    return json.dumps(data) + "\n"


async def ensure_dir(path: Path) -> None:
    """Асинхронно создаёт директорию если её нет."""
    path.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """Очищает имя файла от опасных символов."""
    # Простая реализация: оставляем только буквы, цифры, точку, дефис, подчёркивание
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9._\-]', '_', filename)
    # Убираем множественные подчёркивания
    safe_name = re.sub(r'_+', '_', safe_name)
    return safe_name
