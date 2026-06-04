"""add teacher decisions and final feedback fields to review tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-04
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("teacher_feedback", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("feedback_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("review_items", sa.Column("teacher_decision", sa.String(16), nullable=True))
    op.add_column("review_items", sa.Column("teacher_comments", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("review_items", "teacher_comments")
    op.drop_column("review_items", "teacher_decision")
    op.drop_column("reviews", "feedback_sent_at")
    op.drop_column("reviews", "teacher_feedback")
