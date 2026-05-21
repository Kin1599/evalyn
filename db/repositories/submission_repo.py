from abc import abstractmethod
from typing import Optional

from db.models.submission import Submission
from db.repositories.base import AbstractRepository


class AbstractSubmissionRepository(AbstractRepository[Submission]):
    @abstractmethod
    async def get_by_student_and_assignment(
        self, student_id: int, assignment_id: int
    ) -> Optional[Submission]: ...

    @abstractmethod
    async def upsert(
        self,
        student_id: int,
        assignment_id: int,
        content_text: Optional[str] = None,
        file_id: Optional[str] = None,
    ) -> Submission: ...

    @abstractmethod
    async def get_by_assignment(self, assignment_id: int) -> list[Submission]: ...

    @abstractmethod
    async def get_by_assignment_list(self, assignment_ids: list[int]) -> list[Submission]: ...
