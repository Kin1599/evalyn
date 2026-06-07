"""add review strengths

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("strengths_json", sa.Text(), nullable=True))
    op.add_column("reviews", sa.Column("weaknesses_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("reviews", "weaknesses_json")
    op.drop_column("reviews", "strengths_json")
