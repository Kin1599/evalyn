import json
from typing import Any

from pydantic import ValidationError

from agents.llm_client import chat
from agents.output_schema import AgentOutput
from agents.prompt_builder import build_code_review_prompt
from agents.sandbox import is_python_code, run_python_code
from core.config import settings


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("В ответе модели не найден JSON-объект.")
    return text[start : end + 1]


def _sandbox_summary(sandbox: Any) -> str:
    if sandbox.error:
        return f"Выполнение не завершилось: {sandbox.error}"
    if sandbox.timed_out:
        return "Превышено время выполнения."
    result = "Выполнение завершено успешно." if sandbox.success else "Выполнение завершено с ошибками."
    if sandbox.stdout:
        result += f"\nstdout:\n{sandbox.stdout}"
    if sandbox.stderr:
        result += f"\nstderr:\n{sandbox.stderr}"
    return result


class BaseAgent:
    def __init__(self, model: str, temperature: float = 0.2) -> None:
        self.model = model
        self.temperature = temperature


class CodeReviewAgent(BaseAgent):
    async def review_submission(
        self,
        assignment_title: str,
        assignment_description: str,
        assignment_criteria: str | None,
        submission_text: str,
        system_prompt: str | None = None,
    ) -> tuple[AgentOutput | str, str]:
        sandbox_summary = None
        if is_python_code(submission_text):
            sandbox = await run_python_code(submission_text)
            sandbox_summary = _sandbox_summary(sandbox)

        messages = build_code_review_prompt(
            assignment_title=assignment_title,
            assignment_description=assignment_description,
            assignment_criteria=assignment_criteria,
            submission_text=submission_text,
            sandbox_summary=sandbox_summary,
            system_prompt_override=system_prompt,
        )

        raw = await chat(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=1300,
        )

        try:
            body = json.loads(_extract_json(raw))
        except Exception as exc:
            return (
                "Не удалось разобрать ответ модели. "
                "Ответ модели:\n" + raw.strip() + f"\n\nОшибка разбора: {exc}",
                raw,
            )

        try:
            return AgentOutput.model_validate(body), raw
        except ValidationError as exc:
            return (
                "JSON модели не соответствует схеме. "
                "Ответ модели:\n" + raw.strip() + f"\n\nОшибка валидации: {exc}",
                raw,
            )


def create_default_reviewer() -> CodeReviewAgent:
    return CodeReviewAgent(model=settings.default_agent_model)
