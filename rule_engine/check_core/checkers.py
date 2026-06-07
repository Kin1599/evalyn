"""
Чекеры условий: ExpressionChecker, LLMChecker, ScriptChecker.
"""

import logging
from typing import Any

from .models import (
    ExpressionCheck,
    LLMCheck,
    ScriptCheck,
    Annotation,
    ExecutionContext,
)
from .exceptions import CheckConditionError

logger = logging.getLogger(__name__)


class ExpressionChecker:
    """Проверка Python-выражений."""

    def check(self, condition: ExpressionCheck, session) -> list[Annotation]:
        """
        Вычисляет выражение, подставляя алиасы вместо имён,
        и сравнивает с ожидаемым значением.
        """
        # Строим локальное пространство имён: алиасы указывают на реальные объекты
        local_vars = {}
        for alias, real_name in session.aliases.items():
            if real_name in session.context.globals:
                local_vars[alias] = session.context.globals[real_name]

        # Добавляем глобальные переменные на случай, если выражение ссылается на них напрямую
        eval_globals = session.context.globals.copy()
        eval_locals = local_vars.copy()

        try:
            result = eval(condition.expression, eval_globals, eval_locals)
        except Exception as e:
            return [Annotation(
                severity="error",
                message=f"Ошибка вычисления выражения '{condition.expression}': {e}",
                location=None
            )]

        # Сравнение с ожидаемым значением
        if condition.tolerance > 0 and isinstance(result, (int, float)) and isinstance(condition.expected, (int, float)):
            if abs(result - condition.expected) > condition.tolerance:
                return [Annotation(
                    severity="error",
                    message=condition.message or f"Ожидалось {condition.expected}, получено {result}",
                    location=None
                )]
        else:
            # Простое сравнение
            if result != condition.expected:
                return [Annotation(
                    severity="error",
                    message=condition.message or f"Ожидалось {condition.expected}, получено {result}",
                    location=None
                )]

        return []  # Проверка пройдена


class LLMChecker:
    """Проверка с помощью языковой модели."""

    def __init__(self, llm_service):
        self.llm = llm_service

    def check(self, condition: LLMCheck, session) -> list[Annotation]:
        """
        Формирует промпт с данными из context_sources и отправляет LLM.
        Ответ должен быть списком аннотаций в JSON или просто текстом.
        """
        # Собираем данные для подстановки
        context_data = {}
        for alias in condition.context_sources:
            real_name = session.aliases.get(alias, alias)
            if real_name in session.context.globals:
                obj = session.context.globals[real_name]
                # Пытаемся представить объект строкой
                try:
                    context_data[alias] = str(obj)[:1000]  # ограничим длину
                except Exception:
                    context_data[alias] = "<не удалось преобразовать в строку>"
            else:
                context_data[alias] = "<не найдено>"

        # Подставляем в шаблон
        try:
            prompt = condition.prompt_template.format(**context_data)
        except KeyError as e:
            return [Annotation(
                severity="error",
                message=f"Ошибка в шаблоне промпта: отсутствует ключ {e}",
                location=None
            )]

        try:
            response = self.llm.ask(prompt)
        except Exception as e:
            return [Annotation(
                severity="error",
                message=f"Ошибка при обращении к LLM: {e}",
                location=None
            )]

        # Интерпретация ответа
        if condition.output_type == "annotations":
            # Ожидаем, что LLM вернёт JSON-список аннотаций
            import json
            try:
                # Ищем JSON в ответе (может быть обёрнут в ```json)
                json_str = response
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0]
                annotations_data = json.loads(json_str)
                return [
                    Annotation(
                        severity=item.get("severity", "info"),
                        message=item.get("message", ""),
                        location=item.get("location")
                    )
                    for item in annotations_data
                ]
            except Exception:
                # Если не получилось, возвращаем как одну аннотацию
                return [Annotation(
                    severity="info",
                    message=response.strip(),
                    location=None
                )]
        else:
            # Другие типы output_type можно добавить позже
            return [Annotation(
                severity="info",
                message=response.strip(),
                location=None
            )]


class ScriptChecker:
    """Выполнение проверочного скрипта."""

    def __init__(self, llm_service=None):
        self.llm = llm_service

    def check(self, condition: ScriptCheck, session) -> list[Annotation]:
        """
        Выполняет скрипт в изолированном пространстве имён,
        предоставляя объект check и переменные контекста.
        """
        annotations = []
        scores = {}

        # Объект check
        class CheckAPI:
            def annotate(self, severity, message, location=None):
                annotations.append(Annotation(severity=severity, message=message, location=location))

            def set_score(self, block_id, score):
                scores[block_id] = score

            def ask_llm(self, prompt):
                if not self.llm:
                    return "LLM не доступен"
                try:
                    return self.llm.ask(prompt)
                except Exception as e:
                    return f"Ошибка LLM: {e}"

        check_api = CheckAPI()
        # Передаём llm_service в check_api (некрасиво, но для простоты)
        check_api.llm = self.llm

        # Готовим глобальные переменные для скрипта
        script_globals = session.context.globals.copy()
        # Добавляем алиасы как переменные с короткими именами
        for alias, real_name in session.aliases.items():
            if real_name in script_globals:
                script_globals[alias] = script_globals[real_name]

        # Добавляем объект check
        script_globals['check'] = check_api

        # Выполняем скрипт
        try:
            exec(condition.script, script_globals)
        except Exception as e:
            annotations.append(Annotation(
                severity="error",
                message=f"Ошибка выполнения проверочного скрипта: {e}",
                location=None
            ))

        return annotations