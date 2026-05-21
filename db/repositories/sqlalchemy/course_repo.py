import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.course import Course, CourseRole
from db.models.user import User
from db.repositories.course_repo import AbstractCourseRepository


class SQLAlchemyCourseRepository(AbstractCourseRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: int) -> Optional[Course]:
        result = await self._session.execute(select(Course).where(Course.id == id))
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Course:
        if "invite_code" not in kwargs:
            kwargs["invite_code"] = secrets.token_hex(4).upper()
        course = Course(**kwargs)
        self._session.add(course)
        await self._session.flush()
        return course

    async def update(self, id: int, **kwargs) -> Optional[Course]:
        course = await self.get_by_id(id)
        if not course:
            return None
        for k, v in kwargs.items():
            setattr(course, k, v)
        await self._session.flush()
        return course

    async def delete(self, id: int) -> bool:
        course = await self.get_by_id(id)
        if not course:
            return False
        await self._session.delete(course)
        return True

    async def get_by_invite_code(self, code: str) -> Optional[Course]:
        result = await self._session.execute(
            select(Course).where(Course.invite_code == code.strip().upper())
        )
        return result.scalar_one_or_none()

    async def get_courses_by_role(self, user_id: int, role: str) -> list[Course]:
        result = await self._session.execute(
            select(Course)
            .join(CourseRole, CourseRole.course_id == Course.id)
            .where(CourseRole.user_id == user_id, CourseRole.role == role)
            .order_by(Course.created_at)
        )
        return list(result.scalars().all())

    async def get_role(self, user_id: int, course_id: int) -> Optional[CourseRole]:
        result = await self._session.execute(
            select(CourseRole).where(
                CourseRole.user_id == user_id,
                CourseRole.course_id == course_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_member(self, user_id: int, course_id: int, role: str) -> CourseRole:
        cr = CourseRole(user_id=user_id, course_id=course_id, role=role)
        self._session.add(cr)
        await self._session.flush()
        return cr

    async def get_members(self, course_id: int, role: str) -> list[User]:
        result = await self._session.execute(
            select(User)
            .join(CourseRole, CourseRole.user_id == User.telegram_id)
            .where(CourseRole.course_id == course_id, CourseRole.role == role)
            .order_by(User.name)
        )
        return list(result.scalars().all())
