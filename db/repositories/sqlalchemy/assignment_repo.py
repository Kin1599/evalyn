from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.assignment import Assignment
from db.repositories.assignment_repo import AbstractAssignmentRepository


class SQLAlchemyAssignmentRepository(AbstractAssignmentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: int) -> Optional[Assignment]:
        result = await self._session.execute(select(Assignment).where(Assignment.id == id))
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Assignment:
        assignment = Assignment(**kwargs)
        self._session.add(assignment)
        await self._session.flush()
        return assignment

    async def update(self, id: int, **kwargs) -> Optional[Assignment]:
        assignment = await self.get_by_id(id)
        if not assignment:
            return None
        for k, v in kwargs.items():
            setattr(assignment, k, v)
        await self._session.flush()
        return assignment

    async def delete(self, id: int) -> bool:
        assignment = await self.get_by_id(id)
        if not assignment:
            return False
        await self._session.delete(assignment)
        return True

    async def get_by_course(self, course_id: int) -> list[Assignment]:
        result = await self._session.execute(
            select(Assignment)
            .where(Assignment.course_id == course_id)
            .order_by(Assignment.created_at)
        )
        return list(result.scalars().all())
