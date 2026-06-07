"""add assignment review settings

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("review_model", sa.String(length=128), nullable=True))
    op.add_column("assignments", sa.Column("review_temperature", sa.Float(), nullable=True))
    op.add_column("assignments", sa.Column("review_system_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("assignments", "review_system_prompt")
    op.drop_column("assignments", "review_temperature")
    op.drop_column("assignments", "review_model")
