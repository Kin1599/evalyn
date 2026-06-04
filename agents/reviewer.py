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
        raise ValueError("No JSON object found in model response.")
    return text[start : end + 1]


def _sandbox_summary(sandbox: Any) -> str:
    if sandbox.error:
        return f"Execution was not completed: {sandbox.error}"
    if sandbox.timed_out:
        return "Execution timed out."
    result = "Execution finished successfully." if sandbox.success else "Execution finished with errors."
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
                "Unable to parse model response. "
                "Model response:\n" + raw.strip() + f"\n\nParse error: {exc}",
                raw,
            )

        try:
            return AgentOutput.model_validate(body), raw
        except ValidationError as exc:
            return (
                "Model JSON does not match schema. "
                "Model response:\n" + raw.strip() + f"\n\nValidation error: {exc}",
                raw,
            )


def create_default_reviewer() -> CodeReviewAgent:
    return CodeReviewAgent(model=settings.default_agent_model)
