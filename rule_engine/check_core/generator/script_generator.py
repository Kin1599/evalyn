"""
Script Generator — генерация проверочных скриптов с помощью LLM.

Используется на этапе создания правила (преподавателем).
Не используется в рантайме проверки.
"""

import logging
from typing import Any

from ..llm.service import BaseLLMService

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """
    Генерирует код Python-скрипта для ScriptCheck
    на основе описания проверки и примера контекста.
    """

    SYSTEM_PROMPT = (
        "Ты — генератор проверочных скриптов для библиотеки Check Core. "
        "Твоя задача — написать Python-код, который проверяет студенческую работу "
        "на соответствие заданию.\n\n"
        "У тебя есть доступ к объекту `check` со следующими методами:\n"
        "- check.annotate(severity, message, location=None) — добавить аннотацию.\n"
        "  severity: 'error', 'warning', 'positive', 'info'\n"
        "  message: текст замечания\n"
        "  location: cell_id или None\n"
        "- check.set_score(block_id, score) — выставить баллы за блок.\n"
        "- check.ask_llm(prompt) — задать вопрос LLM (возвращает строку).\n\n"
        "Также тебе доступны:\n"
        "- все переменные из context.globals по их реальным именам\n"
        "- алиасы из спецификации InputSpec\n\n"
        "ПРАВИЛА:\n"
        "1. Пиши только код, без markdown-блоков и пояснений.\n"
        "2. Код должен быть безопасным и не модифицировать глобальное состояние.\n"
        "3. Не используй import'ы сторонних библиотек (только стандартная библиотека и то, "
        "что уже есть в окружении).\n"
        "4. Для сложных проверок используй check.ask_llm().\n"
        "5. Всегда проверяй, что переменные существуют перед использованием.\n"
        "6. В случае ошибок добавляй информативные аннотации.\n"
    )

    def __init__(self, llm_service: BaseLLMService):
        self._llm = llm_service

    def generate(
        self,
        description: str,
        example_context: dict[str, Any] | None = None,
        additional_hints: str = "",
    ) -> str:
        """
        Генерирует код проверочного скрипта.

        Args:
            description: текстовое описание проверки (что проверяем).
            example_context: пример переменных, доступных в контексте
                           (словарь имя -> значение/тип).
            additional_hints: дополнительные указания для генерации.

        Returns:
            Строка с Python-кодом скрипта.

        Raises:
            RuntimeError: если LLM не смогла сгенерировать код.
        """
        # Формируем описание контекста
        context_desc = "Неизвестен"
        if example_context:
            items = []
            for name, value in example_context.items():
                type_name = type(value).__name__
                try:
                    sample = str(value)[:100]
                except Exception:
                    sample = "<...>"
                items.append(f"- {name}: {type_name} = {sample}")
            context_desc = "\n".join(items) if items else "Пустой контекст"

        prompt = (
            f"Сгенерируй проверочный скрипт.\n\n"
            f"ЗАДАЧА ПРОВЕРКИ:\n{description}\n\n"
            f"ДОСТУПНЫЕ ПЕРЕМЕННЫЕ:\n{context_desc}\n\n"
            f"ДОПОЛНИТЕЛЬНЫЕ УКАЗАНИЯ:\n{additional_hints or 'Отсутствуют'}\n\n"
            f"Сгенерируй только код (без markdown-разметки):"
        )

        try:
            code = self._llm.ask(prompt, system=self.SYSTEM_PROMPT).strip()
        except Exception as e:
            raise RuntimeError(f"Не удалось сгенерировать скрипт: {e}")

        # Очистка от возможных markdown-блоков
        code = self._clean_code(code)

        if not code:
            raise RuntimeError("LLM вернула пустой скрипт")

        logger.info("Сгенерирован скрипт длиной %d символов", len(code))
        return code

    def _clean_code(self, code: str) -> str:
        """Убирает markdown-разметку, если LLM обернула код в ```python ... ```."""
        code = code.strip()
        # Удаляем ```python в начале
        if code.startswith("```"):
            first_newline = code.find("\n")
            if first_newline != -1:
                code = code[first_newline + 1:]
        # Удаляем ``` в конце
        if code.endswith("```"):
            code = code[:-3]
        return code.strip()