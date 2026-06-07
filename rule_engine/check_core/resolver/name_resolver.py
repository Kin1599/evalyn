"""
Name Resolver — компонент для поиска переменных в контексте выполнения.

Реализует три стратегии поиска:
- strict: точное совпадение имени
- rule: фильтрация по типу и ограничениям
- llm: поиск с помощью языковой модели
- auto: последовательное применение rule -> llm при неоднозначности
"""

import logging
from typing import Any, Optional

from ..models import InputSpec, ExecutionContext
from ..exceptions import ResolutionError

logger = logging.getLogger(__name__)


class NameResolver:
    """
    Поиск объектов в контексте выполнения по спецификации InputSpec.
    """

    def __init__(self, llm_service=None):
        """
        Args:
            llm_service: экземпляр LLMService для стратегии llm/auto.
                        Если None, стратегии llm недоступны.
        """
        self._llm_service = llm_service

    def resolve(
        self,
        spec: InputSpec,
        context: ExecutionContext,
        aliases: dict[str, str],
    ) -> str:
        """
        Находит реальное имя переменной по спецификации.

        Args:
            spec: спецификация поиска.
            context: контекст выполнения (содержит globals).
            aliases: уже разрешённые алиасы (для зависимых поисков).

        Returns:
            Реальное имя переменной в context.globals.

        Raises:
            ResolutionError: если объект не найден или найден неоднозначно.
        """
        strategy = spec.search_strategy

        if strategy == "strict":
            return self._resolve_strict(spec, context)
        elif strategy == "rule":
            return self._resolve_rule(spec, context)
        elif strategy == "llm":
            return self._resolve_llm(spec, context)
        elif strategy == "auto":
            return self._resolve_auto(spec, context)
        else:
            raise ResolutionError(f"Неизвестная стратегия поиска: {strategy}")

    # ──────────────────────────────────────────────
    #  strict
    # ──────────────────────────────────────────────

    def _resolve_strict(self, spec: InputSpec, context: ExecutionContext) -> str:
        """Поиск по точному имени переменной."""
        name = spec.expected_name
        if not name:
            raise ResolutionError("Стратегия strict требует expected_name")

        if name not in context.globals:
            raise ResolutionError(
                f"Переменная '{name}' не найдена в контексте. "
                f"Доступные переменные: {list(context.globals.keys())}"
            )

        return name

    # ──────────────────────────────────────────────
    #  rule
    # ──────────────────────────────────────────────

    def _resolve_rule(self, spec: InputSpec, context: ExecutionContext) -> str:
        """
        Фильтрует context.globals по ограничениям из spec.constraints.
        Если кандидат ровно один — возвращает его.
        Если несколько — зависит от search_strategy:
          "rule" -> ResolutionError (неоднозначность)
          "auto" -> делегирует в _resolve_llm
        """
        candidates = self._filter_candidates(spec, context)

        if len(candidates) == 0:
            raise ResolutionError(
                f"Не найдено переменных, удовлетворяющих ограничениям: {spec.constraints}"
            )

        if len(candidates) == 1:
            return candidates[0]

        # Неоднозначность
        if spec.search_strategy == "rule":
            raise ResolutionError(
                f"Найдено несколько кандидатов: {candidates}. "
                f"Уточните ограничения или используйте стратегию auto/llm."
            )

        raise ResolutionError(
            f"Неоднозначность при rule-поиске: {candidates}"
        )

    def _filter_candidates(
        self, spec: InputSpec, context: ExecutionContext
    ) -> list[str]:
        """
        Возвращает список имён переменных из context.globals,
        удовлетворяющих constraints из spec.
        """
        constraints = spec.constraints or {}
        candidates = []

        # Определяем, в каких ячейках искать
        if spec.search_scope == "all":
            search_globals = context.globals
        elif isinstance(spec.search_scope, list):
            # Фильтруем только переменные, определённые в указанных ячейках
            allowed_names = {
                name
                for name, cell_idx in context.variable_cells.items()
                if cell_idx in spec.search_scope
            }
            search_globals = {
                name: val
                for name, val in context.globals.items()
                if name in allowed_names
            }
        else:
            search_globals = context.globals

        for name, value in search_globals.items():
            if self._matches_constraints(name, value, constraints):
                candidates.append(name)

        return candidates

    def _matches_constraints(
        self, name: str, value: Any, constraints: dict
    ) -> bool:
        """
        Проверяет, удовлетворяет ли значение ограничениям.

        Поддерживаемые ключи constraints:
        - type: str — ожидаемый тип (например, "networkx.Graph", "dict")
        - attrs: dict — точные значения атрибутов
        - dict_keys: list — обязательные ключи словаря
        - value_ranges: dict — диапазоны [min, max] для атрибутов/ключей
        """
        # Проверка типа
        expected_type = constraints.get("type")
        if expected_type:
            if not self._check_type(value, expected_type):
                return False

        # Проверка точных значений атрибутов
        attrs = constraints.get("attrs", {})
        for attr_name, expected_value in attrs.items():
            if not hasattr(value, attr_name):
                return False
            actual = getattr(value, attr_name)
            if callable(actual):
                actual = actual()
            if actual != expected_value:
                return False

        # Проверка наличия ключей словаря
        dict_keys = constraints.get("dict_keys", [])
        for key in dict_keys:
            if not isinstance(value, dict) or key not in value:
                return False

        # Проверка диапазонов значений
        value_ranges = constraints.get("value_ranges", {})
        for attr_name, (min_val, max_val) in value_ranges.items():
            if isinstance(value, dict):
                if attr_name not in value:
                    return False
                actual = value[attr_name]
            else:
                if not hasattr(value, attr_name):
                    return False
                actual = getattr(value, attr_name)
                if callable(actual):
                    actual = actual()
            if not (min_val <= actual <= max_val):
                return False

        return True

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """
        Проверяет, соответствует ли значение ожидаемому типу.
        expected_type может быть:
        - "int", "str", "dict", "list" — встроенные типы
        - "networkx.Graph" — полное имя класса
        - "module" — проверка на модуль
        """
        # Встроенные типы
        builtins = {"int": int, "float": float, "str": str, "dict": dict,
                    "list": list, "tuple": tuple, "set": set, "bool": bool}
        if expected_type in builtins:
            return isinstance(value, builtins[expected_type])

        # module
        if expected_type == "module":
            return hasattr(value, "__name__") and hasattr(value, "__file__")

        # Составные имена (networkx.Graph)
        if "." in expected_type:
            module_name, class_name = expected_type.rsplit(".", 1)
            actual_module = getattr(type(value), "__module__", "")
            actual_class = type(value).__name__
            return actual_module == module_name and actual_class == class_name

        # Просто имя класса
        return type(value).__name__ == expected_type

    # ──────────────────────────────────────────────
    #  llm
    # ──────────────────────────────────────────────

    def _resolve_llm(self, spec: InputSpec, context: ExecutionContext) -> str:
        """Поиск с помощью языковой модели."""
        if not self._llm_service:
            raise ResolutionError("LLM-сервис не настроен")

        candidates = list(context.globals.keys())

        # Формируем описание кандидатов для LLM
        candidates_desc = []
        for i, name in enumerate(candidates):
            value = context.globals[name]
            type_name = type(value).__name__
            try:
                str_repr = str(value)[:200]
            except Exception:
                str_repr = "<не удалось сериализовать>"
            candidates_desc.append(
                f"{i+1}. {name} (тип: {type_name}): {str_repr}"
            )

        prompt = (
            f"Найди переменную по следующему описанию:\n"
            f"Назначение: {spec.type}\n"
            f"Ожидаемые характеристики: {spec.constraints or 'не заданы'}\n\n"
            f"Доступные переменные:\n" + "\n".join(candidates_desc) + "\n\n"
            f"Верни ТОЛЬКО имя переменной (одно слово), которая лучше всего подходит. "
            f"Если ничего не подходит, верни 'NOT_FOUND'."
        )

        try:
            response = self._llm_service.ask(prompt).strip()
        except Exception as e:
            raise ResolutionError(f"Ошибка при обращении к LLM: {e}")

        if response == "NOT_FOUND" or response not in context.globals:
            raise ResolutionError(
                f"LLM не смогла найти подходящую переменную. Ответ: {response}"
            )

        return response

    # ──────────────────────────────────────────────
    #  auto
    # ──────────────────────────────────────────────

    def _resolve_auto(self, spec: InputSpec, context: ExecutionContext) -> str:
        """
        Пробует rule-поиск. Если кандидатов несколько — делегирует в LLM.
        Если LLM недоступен — выбрасывает ошибку неоднозначности.
        """
        try:
            return self._resolve_rule(spec, context)
        except ResolutionError as e:
            if "Найдено несколько кандидатов" in str(e) and self._llm_service:
                logger.info("Неоднозначность rule-поиска, пробуем LLM")
                return self._resolve_llm(spec, context)
            raise