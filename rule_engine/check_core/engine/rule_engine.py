"""
Rule Engine — главный компонент библиотеки Check Core.
Координирует выполнение проверки студенческой работы:
- запуск ноутбука в песочнице,
- разрешение имён переменных,
- выполнение условий (выражения, LLM, скрипты),
- сбор аннотаций.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from ..models import (
    CheckRule,
    CheckBlock,
    InputSpec,
    CheckCondition,
    ExpressionCheck,
    LLMCheck,
    ScriptCheck,
    Annotation,
    ExecutionContext,
    CheckResult,
    Submission
)
from ..exceptions import ResolutionError, CheckCoreError
from ..sandbox.adapter import SandboxAdapter
from ..resolver.name_resolver import NameResolver
from ..checkers import ExpressionChecker, LLMChecker, ScriptChecker
from ..llm.service import BaseLLMService
from ..llm.service import create_llm_service

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Вспомогательные модели входных данных
# ──────────────────────────────────────────────

# @dataclass
# class Submission:
#     """Студенческая работа."""
#     notebook_path: Path
#     additional_files: list[tuple[str, bytes]] = field(default_factory=list)
#     # Каждый элемент — (имя_файла_в_контейнере, содержимое)

from ..config import Config
# @dataclass
# class Config:
#     """Настройки запуска проверки."""
#     # Песочница
#     venv_name: str = "datascience-py311"
#     venv_storage_path: str = "~/.sandbox_data/venvs"
#     containers_path: str = "~/.sandbox_data/containers"
#     sandbox_ttl: int = 600
#     cell_timeout: int = 30

#     # LLM
#     llm_endpoint: Optional[str] = None
#     llm_api_key: Optional[str] = None
#     llm_model: str = "gpt-4o"

#     # Прочее
#     stop_on_error: bool = False  # дублирует правило, если правило не задано
#     max_retries: int = 2


# ──────────────────────────────────────────────
#  Внутренний объект сессии проверки
# ──────────────────────────────────────────────

class Session:
    """Хранит состояние в процессе проверки одной работы."""
    def __init__(self):
        self.context: Optional[ExecutionContext] = None
        self.aliases: dict[str, str] = {}   # alias -> реальное имя переменной
        self.annotations: list[Annotation] = []


# ──────────────────────────────────────────────
#  Rule Engine
# ──────────────────────────────────────────────

class RuleEngine:
    """
    Главный класс библиотеки.
    Принимает правило, работу и конфигурацию, возвращает CheckResult.
    """

    def __init__(
        self,
        sandbox_adapter: Optional[SandboxAdapter] = None,
        name_resolver: Optional[NameResolver] = None,
        expression_checker: Optional[ExpressionChecker] = None,
        llm_checker: Optional[LLMChecker] = None,
        script_checker: Optional[ScriptChecker] = None,
        llm_service: Optional[BaseLLMService] = None,
    ):
        """
        Все зависимости можно внедрить явно.
        Если не переданы, будут созданы в методе run на основе Config.
        """
        self._sandbox_adapter = sandbox_adapter
        self._name_resolver = name_resolver
        self._expression_checker = expression_checker
        self._llm_checker = llm_checker
        self._script_checker = script_checker
        self._llm_service = llm_service

    def run(self, rule: CheckRule, submission: Submission, config: Config) -> CheckResult:
        """
        Выполнить полную проверку работы по правилу.
        """
        # Создаём сервисы, если не были переданы
        

        # В методе run:
        llm_service = self._llm_service or create_llm_service(config)
        sandbox_adapter = self._sandbox_adapter or SandboxAdapter()
        name_resolver = self._name_resolver or NameResolver(llm_service=llm_service)
        expression_checker = self._expression_checker or ExpressionChecker()
        llm_checker = self._llm_checker or LLMChecker(llm_service=llm_service)
        script_checker = self._script_checker or ScriptChecker(llm_service=llm_service)

        # 1. Подготовка сессии
        session = Session()

        # 2. Выполнение ноутбука в песочнице
        try:
            session.context = sandbox_adapter.execute(
                submission=submission,
                stop_on_error=rule.stop_on_error if rule.stop_on_error else config.stop_on_error,
                config=config,
            )
        except CheckCoreError as e:
            logger.error("Ошибка песочницы: %s", e)
            return CheckResult(
                rule_id=rule.rule_id,
                annotations=[Annotation(severity="error", message=f"Ошибка выполнения: {e}")],
            )

        # 3. Обработка блоков правила
        for block in rule.blocks:
            self._process_block(block, session, name_resolver,
                                expression_checker, llm_checker, script_checker)

        # 4. Сбор результатов
        return CheckResult(
            rule_id=rule.rule_id,
            annotations=session.annotations,
            context=session.context,
            scores={},  # баллы пока не реализованы
        )

    def _process_block(
        self,
        block: CheckBlock,
        session: Session,
        name_resolver: NameResolver,
        expression_checker: ExpressionChecker,
        llm_checker: LLMChecker,
        script_checker: ScriptChecker,
    ) -> None:
        """Обрабатывает один CheckBlock: разрешает имена и выполняет условия."""
        logger.info("Обработка блока %s: %s", block.id, block.description)

        # Разрешение всех input-спецификаций
        missing_input = False
        for spec in block.inputs:
            try:
                real_name = name_resolver.resolve(spec, session.context, session.aliases)
                session.aliases[spec.alias] = real_name
                logger.debug("Разрешён %s -> %s", spec.alias, real_name)
            except ResolutionError as e:
                session.annotations.append(
                    Annotation(
                        severity="error",
                        message=f"Не удалось найти {spec.alias}: {e}",
                        location=None,
                    )
                )
                missing_input = True
                break  # если не нашли обязательный объект, пропускаем остальные inputs и условия блока

        if missing_input:
            return  # дальнейшие проверки блока не имеют смысла

        # Выполнение условий
        for condition in block.conditions:
            try:
                if isinstance(condition, ExpressionCheck):
                    annotations = expression_checker.check(condition, session)
                elif isinstance(condition, LLMCheck):
                    annotations = llm_checker.check(condition, session)
                elif isinstance(condition, ScriptCheck):
                    annotations = script_checker.check(condition, session)
                else:
                    logger.warning("Неизвестный тип условия: %s", type(condition))
                    continue
                session.annotations.extend(annotations)
            except Exception as e:
                logger.error("Ошибка при проверке условия: %s", e)
                session.annotations.append(
                    Annotation(
                        severity="error",
                        message=f"Ошибка проверки условия: {e}",
                        location=None,
                    )
                )