from abc import abstractmethod
from typing import Optional

from db.models.review import Review
from db.models.review_item import ReviewItem
from db.repositories.base import AbstractRepository


class AbstractReviewRepository(AbstractRepository[Review]):
    @abstractmethod
    async def create(
        self,
        submission_id: int,
        model: str,
        raw_output: str,
        status: str,
        overall_score: float | None = None,
        summary: str | None = None,
        **kwargs,
    ) -> Review: ...

    @abstractmethod
    async def create_item(
        self,
        review_id: int,
        category: str,
        severity: str,
        title: str,
        description: str,
        location: str | None = None,
        suggestion: str | None = None,
    ) -> ReviewItem: ...

    @abstractmethod
    async def get_by_submission(self, submission_id: int) -> list[Review]: ...

    @abstractmethod
    async def get_latest_by_submission(self, submission_id: int) -> Review | None: ...

    @abstractmethod
    async def get_items_by_review(self, review_id: int) -> list[ReviewItem]: ...

    @abstractmethod
    async def get_item_by_id(self, item_id: int) -> Optional[ReviewItem]: ...

    @abstractmethod
    async def update_item(self, id: int, **kwargs) -> Optional[ReviewItem]: ...
