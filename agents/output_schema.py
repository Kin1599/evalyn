from typing import Literal

from pydantic import BaseModel, Field


class ReviewItemOutput(BaseModel):
    category: str = Field(..., description="code_style, logic, tests, docs, performance, security")
    severity: Literal["error", "warning", "suggestion"]
    title: str
    description: str
    location: str | None = None
    suggestion: str | None = None


class AgentOutput(BaseModel):
    overall_score: float = Field(..., ge=0.0, le=10.0)
    summary: str
    items: list[ReviewItemOutput]
    strengths: list[str] = []
