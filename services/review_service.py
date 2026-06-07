from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agents.output_schema import AgentOutput
from agents.reviewer import CodeReviewAgent
from db.models.submission import Submission
from services.hw_checker_service import run_assignment_rule_engine, serialize_check_result


@dataclass(slots=True)
class ReviewExecutionResult:
    outcome: AgentOutput | str
    raw_output: str


async def run_code_review(
    *,
    assignment_title: str,
    assignment_description: str,
    assignment_criteria: str | None,
    submission_text: str,
    model: str,
    temperature: float = 0.2,
    system_prompt: str | None = None,
) -> ReviewExecutionResult:
    agent = CodeReviewAgent(model=model, temperature=temperature)
    outcome, raw_output = await agent.review_submission(
        assignment_title=assignment_title,
        assignment_description=assignment_description,
        assignment_criteria=assignment_criteria,
        submission_text=submission_text,
        system_prompt=system_prompt,
    )
    return ReviewExecutionResult(outcome=outcome, raw_output=raw_output)


async def run_assignment_review(
    *,
    assignment: Any,
    submission_text: str,
    model: str,
    temperature: float = 0.2,
    system_prompt: str | None = None,
) -> ReviewExecutionResult:
    if getattr(assignment, "check_mode", "llm") == "rule" and getattr(assignment, "rule_config_json", None):
        rule_result = await run_assignment_rule_engine(
            rule_json=assignment.rule_config_json,
            notebook_text=submission_text,
        )
        return ReviewExecutionResult(
            outcome=serialize_check_result(rule_result.check_result),
            raw_output=json.dumps(rule_result.raw_rule, ensure_ascii=False),
        )

    review_model = getattr(assignment, "review_model", None) or model
    review_temperature = getattr(assignment, "review_temperature", None)
    if review_temperature is None:
        review_temperature = temperature
    review_system_prompt = getattr(assignment, "review_system_prompt", None) or system_prompt

    return await run_code_review(
        assignment_title=assignment.title,
        assignment_description=assignment.description,
        assignment_criteria=assignment.criteria,
        submission_text=submission_text,
        model=review_model,
        temperature=review_temperature,
        system_prompt=review_system_prompt,
    )


async def store_review(
    *,
    uow: Any,
    submission: Submission,
    model: str,
    result: AgentOutput | dict | str,
    raw_output: str,
    temperature: float | None = None,
    system_prompt: str | None = None,
):
    if isinstance(result, dict):
        annotations = result.get("annotations", [])
        summary = f"Rule engine returned {len(annotations)} annotations."
        review = await uow.reviews.create(
            submission_id=submission.id,
            model=model,
            raw_output=raw_output,
            status="pending_moderation" if annotations else "done",
            overall_score=None,
            summary=summary,
        )
        for item in annotations:
            await uow.reviews.create_item(
                review_id=review.id,
                category=str(item.get("category", "rule_engine")),
                severity=str(item.get("severity", "suggestion")),
                title=str(item.get("message", "Rule engine annotation")),
                description=str(item.get("message", "")),
                location=item.get("location"),
                suggestion=None,
            )
        await uow.submissions.update(submission.id, status="reviewed")
        return review

    review = await uow.reviews.create(
        submission_id=submission.id,
        model=model,
        raw_output=raw_output,
        status="pending_moderation" if isinstance(result, AgentOutput) else "failed",
        overall_score=result.overall_score if isinstance(result, AgentOutput) else None,
        summary=result.summary if isinstance(result, AgentOutput) else str(result),
        strengths_json=json.dumps(result.strengths, ensure_ascii=False) if isinstance(result, AgentOutput) else None,
        weaknesses_json=json.dumps(result.weaknesses, ensure_ascii=False) if isinstance(result, AgentOutput) else None,
    )
    if isinstance(result, AgentOutput):
        for item in result.items:
            await uow.reviews.create_item(
                review_id=review.id,
                category=item.category,
                severity=item.severity,
                title=item.title,
                description=item.description,
                location=item.location,
                suggestion=item.suggestion,
            )
        await uow.submissions.update(submission.id, status="reviewed")
    return review
