from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.submission import Submission
from db.repositories.submission_repo import AbstractSubmissionRepository


class SQLAlchemySubmissionRepository(AbstractSubmissionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: int) -> Optional[Submission]:
        result = await self._session.execute(select(Submission).where(Submission.id == id))
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Submission:
        submission = Submission(**kwargs)
        self._session.add(submission)
        await self._session.flush()
        return submission

    async def update(self, id: int, **kwargs) -> Optional[Submission]:
        submission = await self.get_by_id(id)
        if not submission:
            return None
        for k, v in kwargs.items():
            setattr(submission, k, v)
        await self._session.flush()
        return submission

    async def delete(self, id: int) -> bool:
        submission = await self.get_by_id(id)
        if not submission:
            return False
        await self._session.delete(submission)
        return True

    async def get_by_student_and_assignment(
        self, student_id: int, assignment_id: int
    ) -> Optional[Submission]:
        result = await self._session.execute(
            select(Submission).where(
                Submission.student_id == student_id,
                Submission.assignment_id == assignment_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        student_id: int,
        assignment_id: int,
        content_text: Optional[str] = None,
        file_id: Optional[str] = None,
    ) -> Submission:
        existing = await self.get_by_student_and_assignment(student_id, assignment_id)
        if existing:
            existing.content_text = content_text
            existing.file_id = file_id
            existing.status = "pending"
            await self._session.flush()
            return existing
        submission = Submission(
            student_id=student_id,
            assignment_id=assignment_id,
            content_text=content_text,
            file_id=file_id,
            status="pending",
        )
        self._session.add(submission)
        await self._session.flush()
        return submission

    async def get_by_assignment(self, assignment_id: int) -> list[Submission]:
        result = await self._session.execute(
            select(Submission).where(Submission.assignment_id == assignment_id)
        )
        return list(result.scalars().all())

    async def get_by_assignment_list(self, assignment_ids: list[int]) -> list[Submission]:
        if not assignment_ids:
            return []
        result = await self._session.execute(
            select(Submission).where(Submission.assignment_id.in_(assignment_ids))
        )
        return list(result.scalars().all())
