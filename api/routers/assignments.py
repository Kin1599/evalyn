from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from db.base import get_async_session
from db.models.assignment import Assignment
from db.repositories.sqlalchemy.assignment_repo import SQLAlchemyAssignmentRepository

router = APIRouter()


class AssignmentRuleUpdate(BaseModel):
    check_mode: str = Field(default="llm", pattern="^(llm|rule)$")
    rule_config_json: str | None = None


@router.get("/course/{course_id}", response_model=List[dict])
async def get_course_assignments(
    course_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get all assignments in a course"""
    try:
        repo = SQLAlchemyAssignmentRepository(session)
        assignments = await repo.get_by_course(course_id)
        
        return [
            {
                "id": assignment.id,
                "title": assignment.title,
                "description": assignment.description,
                "criteria": assignment.criteria,
                "deadline": assignment.deadline.isoformat() if assignment.deadline else None,
                "created_at": assignment.created_at.isoformat(),
            }
            for assignment in assignments
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching assignments: {exc}")


@router.get("/{assignment_id}", response_model=dict)
async def get_assignment(
    assignment_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get assignment details"""
    try:
        repo = SQLAlchemyAssignmentRepository(session)
        assignment = await repo.get_by_id(assignment_id)
        
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        return {
            "id": assignment.id,
            "course_id": assignment.course_id,
            "title": assignment.title,
            "description": assignment.description,
            "criteria": assignment.criteria,
            "check_mode": getattr(assignment, "check_mode", "llm"),
            "rule_config_json": getattr(assignment, "rule_config_json", None),
            "deadline": assignment.deadline.isoformat() if assignment.deadline else None,
            "created_at": assignment.created_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching assignment: {exc}")


@router.put("/{assignment_id}/rules", response_model=dict)
async def update_assignment_rules(
    assignment_id: int,
    payload: AssignmentRuleUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = SQLAlchemyAssignmentRepository(session)
        assignment = await repo.get_by_id(assignment_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")

        updated = await repo.update(
            assignment_id,
            check_mode=payload.check_mode,
            rule_config_json=payload.rule_config_json,
        )
        await session.commit()
        return {
            "id": updated.id,
            "check_mode": updated.check_mode,
            "rule_config_json": updated.rule_config_json,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error updating assignment rules: {exc}")
