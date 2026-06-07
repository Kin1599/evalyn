"""
Модели данных библиотеки Check Core.

Все классы используют dataclasses для простоты сериализации
и интеграции с внешними системами. Pydantic не используется
намеренно — модельки тонкие, валидация на уровне RuleEngine.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union


# ──────────────────────────────────────────────
#  Правило проверки
# ──────────────────────────────────────────────

@dataclass
class CheckBlock:
    """Один блок проверки — обычно подпункт задания."""
    id: str
    description: str
    inputs: list["InputSpec"] = field(default_factory=list)
    conditions: list["CheckCondition"] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class GradingConfig:
    """Конфигурация начисления баллов (опционально)."""
    max_score: float = 0.0
    passing_score: float = 0.0


@dataclass
class CheckRule:
    """Полное правило проверки работы."""
    rule_id: str
    blocks: list[CheckBlock] = field(default_factory=list)
    stop_on_error: bool = False
    grading: Optional[GradingConfig] = None


# ──────────────────────────────────────────────
#  Входные спецификации (что ищем в работе)
# ──────────────────────────────────────────────

@dataclass
class InputSpec:
    """Описание объекта, который нужно найти в окружении студента."""
    alias: str                           # имя для использования в условиях
    type: str                            # "variable", "function", "class", "image", "text"
    search_strategy: str = "auto"        # "strict", "rule", "llm", "auto"
    strict_name: bool = False
    expected_name: Optional[str] = None   # точное имя при strict
    constraints: Optional[dict] = None    # фильтры для rule-based поиска
    search_scope: Union[str, list[int]] = "all"  # "all" или список индексов ячеек


# ──────────────────────────────────────────────
#  Условия проверки
# ──────────────────────────────────────────────

@dataclass
class CheckCondition:
    """Базовый класс условия проверки."""
    pass


@dataclass
class ExpressionCheck(CheckCondition):
    """Проверка через Python-выражение."""
    expression: str
    expected: Any = None
    tolerance: float = 0.0
    message: str = ""


@dataclass
class LLMCheck(CheckCondition):
    """Проверка с помощью языковой модели."""
    prompt_template: str
    context_sources: list[str] = field(default_factory=list)
    output_type: str = "annotations"


@dataclass
class ScriptCheck(CheckCondition):
    """Проверка через выполнение скрипта."""
    script: str
    generated: bool = False


# ──────────────────────────────────────────────
#  Аннотации (результат проверки)
# ──────────────────────────────────────────────

@dataclass
class Annotation:
    """Одна аннотация — замечание, ошибка или похвала."""
    severity: str        # "error", "warning", "positive", "info"
    message: str
    location: Optional[str] = None   # cell_id или None


# ──────────────────────────────────────────────
#  Контекст выполнения
# ──────────────────────────────────────────────

@dataclass
class ExecutedCell:
    """Результат выполнения одной ячейки."""
    cell_id: str
    source: str
    stdout: str = ""
    error: Optional[dict] = None    # {"ename": ..., "evalue": ..., "traceback": [...]}
    images: list[bytes] = field(default_factory=list)


@dataclass
class ExecutionContext:
    """Состояние после выполнения всех ячеек."""
    globals: dict[str, Any] = field(default_factory=dict)
    cells: list[ExecutedCell] = field(default_factory=list)
    variable_cells: dict[str, int] = field(default_factory=dict)


# ──────────────────────────────────────────────
#  Результат всей проверки
# ──────────────────────────────────────────────

@dataclass
class CheckResult:
    """Финальный результат проверки работы."""
    rule_id: str = ""
    annotations: list[Annotation] = field(default_factory=list)
    context: Optional[ExecutionContext] = None
    scores: dict[str, float] = field(default_factory=dict)

@dataclass
class Submission:
    notebook_path: Path
    additional_files: list[tuple[str, bytes]] = field(default_factory=list)