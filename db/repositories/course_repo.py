from abc import abstractmethod

from db.models.course import Course, CourseRole
from db.models.user import User
from db.repositories.base import AbstractRepository


class AbstractCourseRepository(AbstractRepository[Course]):
    @abstractmethod
    async def get_by_invite_code(self, code: str) -> Course | None: ...

    @abstractmethod
    async def get_courses_by_role(self, user_id: int, role: str) -> list[Course]: ...

    @abstractmethod
    async def get_role(self, user_id: int, course_id: int) -> CourseRole | None: ...

    @abstractmethod
    async def add_member(self, user_id: int, course_id: int, role: str) -> CourseRole: ...

    @abstractmethod
    async def get_members(self, course_id: int, role: str) -> list[User]: ...
