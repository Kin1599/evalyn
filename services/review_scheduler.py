from __future__ import annotations

import asyncio
import logging

from core.config import settings
from services.review_service import run_assignment_review, store_review

logger = logging.getLogger(__name__)


async def process_pending_assignment_reviews(uow_factory) -> int:
    processed = 0
    async with uow_factory() as uow:
        assignments = await uow.assignments.get_all()
        assignments_by_id = {assignment.id: assignment for assignment in assignments}
        pending_assignment_ids = [assignment.id for assignment in assignments if not getattr(assignment, "is_private", False)]
        submissions = await uow.submissions.get_by_assignment_list(pending_assignment_ids) if pending_assignment_ids else []

        for submission in submissions:
            if submission.status != "pending":
                continue
            assignment = assignments_by_id.get(submission.assignment_id)
            if not assignment:
                continue
            submission_text = submission.content_text or ""
            if not submission_text and submission.file_id:
                continue
            if not submission_text:
                continue
            review_result = await run_assignment_review(
                assignment=assignment,
                submission_text=submission_text,
                model=assignment.review_model or settings.default_agent_model,
                temperature=assignment.review_temperature or 0.2,
                system_prompt=assignment.review_system_prompt,
            )
            await store_review(
                uow=uow,
                submission=submission,
                model=assignment.review_model or settings.default_agent_model,
                result=review_result.outcome,
                raw_output=review_result.raw_output,
            )
            processed += 1

        await uow.commit()
    return processed


async def review_scheduler_loop(uow_factory, stop_event: asyncio.Event) -> None:
    interval = max(30, int(settings.assignment_review_interval_seconds))
    while not stop_event.is_set():
        try:
            processed = await process_pending_assignment_reviews(uow_factory)
            if processed:
                logger.info("Обработано %s ожидающих проверок заданий", processed)
        except Exception:
            logger.exception("Сбой планировщика проверки заданий")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
