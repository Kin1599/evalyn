from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    materials_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    materials_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    materials_file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    review_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    check_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="llm")
    rule_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Assignment id={self.id} title={self.title!r}>"
