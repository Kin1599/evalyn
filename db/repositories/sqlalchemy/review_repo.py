from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.review import Review
from db.models.review_item import ReviewItem
from db.repositories.review_repo import AbstractReviewRepository


class SQLAlchemyReviewRepository(AbstractReviewRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: int) -> Optional[Review]:
        result = await self._session.execute(select(Review).where(Review.id == id))
        return result.scalar_one_or_none()

    async def create(
        self,
        submission_id: int,
        model: str,
        raw_output: str,
        status: str,
        overall_score: float | None = None,
        summary: str | None = None,
        **kwargs,
    ) -> Review:
        review = Review(
            submission_id=submission_id,
            model=model,
            raw_output=raw_output,
            status=status,
            overall_score=overall_score,
            summary=summary,
        )
        self._session.add(review)
        await self._session.flush()
        return review

    async def update(self, id: int, **kwargs):
        review = await self.get_by_id(id)
        if not review:
            return None
        for key, value in kwargs.items():
            setattr(review, key, value)
        await self._session.flush()
        return review

    async def delete(self, id: int) -> bool:
        review = await self.get_by_id(id)
        if not review:
            return False
        await self._session.delete(review)
        return True

    async def create_item(
        self,
        review_id: int,
        category: str,
        severity: str,
        title: str,
        description: str,
        location: str | None = None,
        suggestion: str | None = None,
    ) -> ReviewItem:
        item = ReviewItem(
            review_id=review_id,
            category=category,
            severity=severity,
            title=title,
            description=description,
            location=location,
            suggestion=suggestion,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def get_by_submission(self, submission_id: int) -> list[Review]:
        result = await self._session.execute(
            select(Review)
            .where(Review.submission_id == submission_id)
            .order_by(Review.id.asc())
        )
        return list(result.scalars().all())

    async def get_latest_by_submission(self, submission_id: int) -> Optional[Review]:
        result = await self._session.execute(
            select(Review)
            .where(Review.submission_id == submission_id)
            .order_by(Review.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_items_by_review(self, review_id: int) -> list[ReviewItem]:
        result = await self._session.execute(select(ReviewItem).where(ReviewItem.review_id == review_id))
        return list(result.scalars().all())

    async def get_item_by_id(self, item_id: int) -> Optional[ReviewItem]:
        result = await self._session.execute(select(ReviewItem).where(ReviewItem.id == item_id))
        return result.scalar_one_or_none()

    async def update_item(self, id: int, **kwargs) -> Optional[ReviewItem]:
        item = await self.get_item_by_id(id)
        if not item:
            return None
        for key, value in kwargs.items():
            setattr(item, key, value)
        await self._session.flush()
        return item
