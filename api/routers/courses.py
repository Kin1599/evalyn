from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from db.base import get_async_session
from db.models.course import Course, CourseRole
from db.repositories.sqlalchemy.course_repo import SQLAlchemyCourseRepository

router = APIRouter()


@router.get("/", response_model=List[dict])
async def get_courses(
    telegram_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get all courses for a user (as owner or student)"""
    try:
        repo = SQLAlchemyCourseRepository(session)
        courses = await repo.get_by_creator(telegram_id)
        student_courses = await repo.get_student_courses(telegram_id)
        
        all_courses = []
        for course in courses:
            all_courses.append({
                "id": course.id,
                "name": course.name,
                "role": "owner",
                "invite_code": course.invite_code,
                "created_at": course.created_at.isoformat(),
            })
        
        for course in student_courses:
            all_courses.append({
                "id": course.id,
                "name": course.name,
                "role": "student",
                "invite_code": course.invite_code,
                "created_at": course.created_at.isoformat(),
            })
        
        return all_courses
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching courses: {exc}")


@router.get("/{course_id}", response_model=dict)
async def get_course(
    course_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get course details"""
    try:
        repo = SQLAlchemyCourseRepository(session)
        course = await repo.get_by_id(course_id)
        
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        
        return {
            "id": course.id,
            "name": course.name,
            "invite_code": course.invite_code,
            "creator_id": course.creator_id,
            "created_at": course.created_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching course: {exc}")


@router.get("/{course_id}/students", response_model=List[dict])
async def get_course_students(
    course_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """Get all students in a course"""
    try:
        repo = SQLAlchemyCourseRepository(session)
        students = await repo.get_students(course_id)
        
        return [
            {
                "telegram_id": student.user.telegram_id,
                "name": student.user.name,
                "username": student.user.username,
                "joined_at": student.joined_at.isoformat(),
            }
            for student in students
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching students: {exc}")
