"""add assignment materials

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("materials_text", sa.Text(), nullable=True))
    op.add_column("assignments", sa.Column("materials_file_id", sa.String(length=256), nullable=True))
    op.add_column("assignments", sa.Column("materials_file_name", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("assignments", "materials_file_name")
    op.drop_column("assignments", "materials_file_id")
    op.drop_column("assignments", "materials_text")
