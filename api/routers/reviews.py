from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from db.base import get_async_session
from db.models.review import Review
from db.repositories.sqlalchemy.review_repo import SQLAlchemyReviewRepository

router = APIRouter()


@router.get("/submission/{submission_id}", response_model=dict)
async def get_submission_review(
    submission_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get review for a submission"""
    try:
        repo = SQLAlchemyReviewRepository(session)
        review = await repo.get_latest_by_submission(submission_id)
        
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        items = [
            {
                "id": item.id,
                "category": item.category,
                "severity": item.severity,
                "title": item.title,
                "description": item.description,
                "location": item.location,
                "suggestion": item.suggestion,
                "teacher_decision": item.teacher_decision,
                "teacher_comments": item.teacher_comments,
            }
            for item in review.items
        ]
        
        return {
            "id": review.id,
            "submission_id": review.submission_id,
            "status": review.status,
            "overall_score": review.overall_score,
            "summary": review.summary,
            "raw_output": review.raw_output[:500] if review.raw_output else None,  # Preview only
            "items": items,
            "teacher_feedback": review.teacher_feedback,
            "feedback_sent_at": review.feedback_sent_at.isoformat() if review.feedback_sent_at else None,
            "created_at": review.created_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching review: {exc}")


@router.get("/", response_model=List[dict])
async def get_recent_reviews(
    limit: int = 10,
    session: AsyncSession = Depends(get_async_session),
):
    """Get recent reviews"""
    try:
        # This would need a method in the repository to get recent reviews
        # For now, return empty list
        return []
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching reviews: {exc}")
