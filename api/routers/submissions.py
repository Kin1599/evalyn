from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from datetime import datetime

from db.base import get_async_session
from db.models.submission import Submission
from db.repositories.sqlalchemy.submission_repo import SQLAlchemySubmissionRepository

router = APIRouter()


@router.get("/assignment/{assignment_id}", response_model=List[dict])
async def get_assignment_submissions(
    assignment_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get all submissions for an assignment"""
    try:
        repo = SQLAlchemySubmissionRepository(session)
        submissions = await repo.get_by_assignment(assignment_id)
        
        return [
            {
                "id": submission.id,
                "assignment_id": submission.assignment_id,
                "student_id": submission.student_id,
                "student_name": submission.student.name if submission.student else "Unknown",
                "status": submission.status,
                "content_preview": (submission.content_text or "")[:200],
                "submitted_at": submission.submitted_at.isoformat(),
            }
            for submission in submissions
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching submissions: {exc}")


@router.get("/{submission_id}", response_model=dict)
async def get_submission(
    submission_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get submission details"""
    try:
        repo = SQLAlchemySubmissionRepository(session)
        submission = await repo.get_by_id(submission_id)
        
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
        
        return {
            "id": submission.id,
            "assignment_id": submission.assignment_id,
            "student_id": submission.student_id,
            "student_name": submission.student.name if submission.student else "Unknown",
            "status": submission.status,
            "content": submission.content_text,
            "submitted_at": submission.submitted_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching submission: {exc}")
