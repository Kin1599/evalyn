from abc import abstractmethod

from db.models.assignment import Assignment
from db.repositories.base import AbstractRepository


class AbstractAssignmentRepository(AbstractRepository[Assignment]):
    @abstractmethod
    async def get_all(self) -> list[Assignment]: ...

    @abstractmethod
    async def get_by_course(self, course_id: int) -> list[Assignment]: ...
